"""
Step 4 extension: ClaimPricingService — single public entry point for claim pricing.

All claim pricing (stored claim, batch, direct) must go through ClaimPricingService.
The service delegates to ClaimOrchestrator for claim-level execution and to
LineOrchestrator for per-line execution. No API, view, or other service should
call ClaimOrchestrator.run() or LineOrchestrator.run() directly; use this service instead.

Step 11 Milestone C: price_claims_bulk() adds snapshot-backed bulk pricing.
ContractPricingConfig is prebuilt once per (contract_id, version_id, service_date) and
reused across all claims that share that key, eliminating repeated DB config lookups.
"""
from datetime import date as date_type
from typing import Dict, List, Optional, Tuple

from core.models import ProviderContract, ClaimHeader
from .config import ClaimPricingInput, ContractPricingConfig
from .types import PricingInput, LineResult, ClaimPricingResult
from .orchestrator import ClaimOrchestrator, LineOrchestrator, _claim_header_to_pricing_input
from .loader import (
    resolve_contract_for_claim,
    resolve_active_contract_version,
    resolve_contract_version,
    build_contract_pricing_config_from_db,
    build_contract_pricing_config_from_version,
)


class ClaimPricingService:
    """
    Single entry point for claim and line pricing. All pricing endpoints must use this service.
    Delegates to ClaimOrchestrator (canonical claim execution order) and LineOrchestrator (per-line).
    """

    def __init__(self):
        self._claim_orchestrator = ClaimOrchestrator()
        self._line_orchestrator = LineOrchestrator()

    def price_claim(
        self,
        claim_input: ClaimPricingInput,
        config: Optional[ContractPricingConfig] = None,
    ) -> ClaimPricingResult:
        """
        Price a claim (stored or batch). Single orchestration path: contract resolution,
        version resolution, line pricing, stop-loss, outlier. All claim pricing must use this method.
        """
        return self._claim_orchestrator.run(claim_input, config=config)

    def price_claim_with_version(
        self,
        contract_id: int,
        version_id: int,
        claim_input: ClaimPricingInput,
    ) -> ClaimPricingResult:
        """
        Step 13: Price a claim against a specific contract version (simulation).
        Bypasses ACTIVE resolver; uses the given version_id directly.
        Allowed version statuses: DRAFT, ACTIVE, SUPERSEDED. ARCHIVED is rejected.
        Does not mutate lifecycle or resolver logic.
        Raises ValueError (400) if version_id not found or does not belong to contract.
        """
        from core.models import ContractVersion

        contract = claim_input.contract
        if contract is None or contract.pk != contract_id:
            contract = ProviderContract.objects.get(pk=contract_id)
            claim_input.contract = contract
            claim_input.contract_id = contract_id

        version = resolve_contract_version(contract_id, version_id)
        if version.status == ContractVersion.VersionStatus.ARCHIVED:
            raise ValueError(
                f"Cannot simulate against ARCHIVED version {version_id}. Use DRAFT, ACTIVE, or SUPERSEDED."
            )

        service_date = claim_input.service_date or date_type.today()
        config = build_contract_pricing_config_from_version(version, service_date)
        return self._claim_orchestrator.run(claim_input, config=config)

    def price_stored_claim(self, claim_header: ClaimHeader) -> ClaimPricingResult:
        """
        Price a stored claim (ClaimHeader). Resolves contract via participation/scope if contract_id is null.
        """
        claim_input = _claim_header_to_pricing_input(claim_header)
        if claim_input.contract is None:
            claim_input.contract = resolve_contract_for_claim(claim_header)
            claim_input.contract_id = claim_input.contract.pk
        return self.price_claim(claim_input)

    def price_claims_bulk(
        self,
        claim_inputs: List[ClaimPricingInput],
    ) -> List[ClaimPricingResult]:
        """
        Step 11 Milestone C: snapshot-backed bulk claim pricing.

        Optimization strategy (no pricing logic changes):
          1. Batch-fetch all unique contracts in one query (no per-claim contract SELECT).
          2. Cache ContractVersion per (contract_pk, service_date) — one query per unique pair.
          3. Cache ContractPricingConfig per (contract_pk, version_pk, service_date) — config
             built once and reused across all claims sharing that key.
          4. ClaimOrchestrator resets the per-line reference-data cache before each claim,
             so line-level caching (Milestone B) remains claim-scoped.

        Pricing correctness invariants:
          - Each claim still follows the canonical execution order:
            contract → version → line pricing → stop-loss → outlier.
          - Execution cache is reset per claim (no bleed across claims).
          - Config is immutable and request-scoped; reuse is safe.
        """
        if not claim_inputs:
            return []

        # Step 1: Batch-fetch missing contracts in one query.
        missing_contract_ids = {
            ci.contract_id
            for ci in claim_inputs
            if ci.contract is None and ci.contract_id is not None
        }
        if missing_contract_ids:
            fetched_contracts: Dict[int, ProviderContract] = {
                c.pk: c
                for c in ProviderContract.objects.filter(pk__in=missing_contract_ids)
            }
            for ci in claim_inputs:
                if ci.contract is None and ci.contract_id in fetched_contracts:
                    ci.contract = fetched_contracts[ci.contract_id]

        # Step 2 & 3: Per-claim: cache version and config; reuse when key matches.
        # Keys:
        #   version_cache : (contract_pk, service_date) → ContractVersion or None
        #   config_cache  : (contract_pk, version_pk_or_None, service_date) → ContractPricingConfig
        version_cache: Dict[Tuple, Optional[object]] = {}
        config_cache: Dict[Tuple, ContractPricingConfig] = {}

        results: List[ClaimPricingResult] = []

        for claim_input in claim_inputs:
            contract = claim_input.contract
            if contract is None:
                raise ValueError(
                    f"ClaimPricingInput with contract_id={claim_input.contract_id} "
                    "could not be resolved to a ProviderContract."
                )

            svc_date: date_type = claim_input.service_date or date_type.today()

            # Version lookup — one DB hit per unique (contract, date) across the whole batch.
            version_key = (contract.pk, svc_date)
            if version_key not in version_cache:
                version_cache[version_key] = resolve_active_contract_version(contract, svc_date)
            version = version_cache[version_key]

            # Config lookup — one DB build per unique (contract, version, date) across the batch.
            config_key = (contract.pk, version.pk if version else None, svc_date)
            if config_key not in config_cache:
                config_cache[config_key] = build_contract_pricing_config_from_db(
                    contract, version, svc_date
                )
            config = config_cache[config_key]

            # Price the claim through the standard orchestration path with the snapshot config.
            # ClaimOrchestrator.run() resets the per-execution line cache before the line loop,
            # ensuring Milestone B caches do not bleed across claims in this batch.
            result = self._claim_orchestrator.run(claim_input, config=config)
            results.append(result)

        return results

    def price_line(
        self,
        contract: ProviderContract,
        request: PricingInput,
        version=None,
        config: Optional[ContractPricingConfig] = None,
    ) -> LineResult:
        """
        Price a single line. Used by single-line endpoint and by ClaimOrchestrator for each line.
        """
        return self._line_orchestrator.run(contract, request, version=version, config=config)

    def price_claim_from_context(
        self, ctx: 'ClaimPricingContext'
    ) -> 'ClaimPricingResult':
        """
        New entry point: consumes a fully-resolved ClaimPricingContext
        produced by PricingContextResolver.
        Delegates to the existing price_claim() method — no new logic.
        """
        from decimal import Decimal

        from core.engine.config import ClaimLineInput, ClaimPricingInput
        from core.engine.types import ClaimPricingContext

        line_inputs = []
        for line in ctx.lines:
            if isinstance(line, dict):
                line_inputs.append(
                    ClaimLineInput(
                        procedure_code=line['procedure_code'],
                        billed_amount=Decimal(str(line['billed_amount'])),
                        units=line.get('units', 1),
                        modifiers=line.get('modifiers', []),
                        cost_amount=(
                            Decimal(str(line['cost_amount']))
                            if line.get('cost_amount') is not None
                            else None
                        ),
                        revenue_code=line.get('revenue_code'),
                    )
                )
            else:
                line_inputs.append(line)

        claim_input = ClaimPricingInput(
            contract_id=ctx.contract_id,
            service_date=ctx.service_date,
            claim_type=ctx.claim_type,
            pricing_date=ctx.pricing_date,
            lines=line_inputs,
            product_id=(
                str(ctx.member.product_id) if ctx.member.product_id is not None else None
            ),
            network_id=(
                str(ctx.member.network_id) if ctx.member.network_id is not None else None
            ),
        )
        return self.price_claim(claim_input)
