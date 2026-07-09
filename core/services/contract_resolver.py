from datetime import date
from typing import Callable

from django.conf import settings
from django.db import models

from core.models import (
    ContractArrangement,
    ContractCoveredEntity,
    ContractScopeUnified,
    ProviderContract,
)


class ContractResolutionError(Exception):
    """Raised when no contract can be resolved for the given context."""

    def __init__(self, message: str, is_oon: bool = False):
        super().__init__(message)
        self.is_oon = is_oon


class ContractResolutionAmbiguityError(Exception):
    """Raised when multiple contracts tie on specificity level and resolution_priority."""

    def __init__(self, message: str, specificity_level: str, contract_ids: list[int]):
        super().__init__(message)
        self.specificity_level = specificity_level
        self.contract_ids = contract_ids


# Entity specificity ranks (higher = more specific). D5.3 precedence ladder rung 2.
RANK_PROVIDER_AT_FACILITY = 50
RANK_PROVIDER = 40
RANK_FACILITY = 30
RANK_ORG_LEAF = 20


class ContractResolver:
    """
    Resolves the best-matching ProviderContract for a given claim context.

    When FEATURE_COVERAGE_RESOLUTION is on, candidates are matched via
    ContractCoveredEntity (facility / provider / org hierarchy). Otherwise
    the legacy provider_org waterfall applies. Both paths filter by claim type
    (ContractArrangement) before tie-breaking.
    """

    def resolve(
        self,
        org_id: str | None,
        network_id: int | None,
        lob: str | None,
        service_date: date,
        product_id: int | None = None,
        org_ids: list[str] | None = None,
        claim_type: str | None = None,
        facility_id: int | None = None,
        provider_id: int | None = None,
    ) -> int:
        org_list = list(org_ids) if org_ids else ([org_id] if org_id else [])
        if not org_list:
            raise ContractResolutionError('Organization not found', is_oon=False)

        if getattr(settings, 'FEATURE_COVERAGE_RESOLUTION', False):
            return self._resolve_by_coverage(
                org_list=org_list,
                network_id=network_id,
                lob=lob,
                service_date=service_date,
                product_id=product_id,
                claim_type=claim_type,
                facility_id=facility_id,
                provider_id=provider_id,
            )

        return self._resolve_by_provider_org(
            org_list=org_list,
            network_id=network_id,
            lob=lob,
            service_date=service_date,
            product_id=product_id,
            claim_type=claim_type,
        )

    def _resolve_by_provider_org(
        self,
        *,
        org_list: list[str],
        network_id: int | None,
        lob: str | None,
        service_date: date,
        product_id: int | None,
        claim_type: str | None,
    ) -> int:
        levels = self._scope_levels(network_id, lob, product_id)
        any_org_contracts = False
        for level_name, match_fn in levels:
            for oid in org_list:
                qs = self._active_contracts_qs(oid, service_date)
                if not qs.exists():
                    continue
                any_org_contracts = True
                matches = match_fn(qs, network_id, service_date, lob, product_id)
                contract_id = self._pick_contract(matches, level_name, claim_type)
                if contract_id is not None:
                    return contract_id

        if not any_org_contracts:
            raise ContractResolutionError(
                f'No contracts found for org(s) {org_list}',
                is_oon=False,
            )

        raise ContractResolutionError(
            f'No matching contract for org(s)={org_list} network={network_id} lob={lob}',
            is_oon=True,
        )

    def _resolve_by_coverage(
        self,
        *,
        org_list: list[str],
        network_id: int | None,
        lob: str | None,
        service_date: date,
        product_id: int | None,
        claim_type: str | None,
        facility_id: int | None,
        provider_id: int | None,
    ) -> int:
        entity_ranks = self._entity_ranks_from_covered_entities(
            org_list=org_list,
            facility_id=facility_id,
            provider_id=provider_id,
            service_date=service_date,
        )
        if not entity_ranks:
            raise ContractResolutionError(
                f'No contracts found for covered entities orgs={org_list}',
                is_oon=False,
            )

        eligible_ids = self._eligible_contract_ids(
            list(entity_ranks.keys()), claim_type,
        )
        entity_ranks = {
            cid: rank for cid, rank in entity_ranks.items() if cid in eligible_ids
        }
        if not entity_ranks:
            raise ContractResolutionError(
                f'No contracts eligible for claim_type={claim_type}',
                is_oon=False,
            )

        qs = ProviderContract.objects.filter(
            contract_id__in=entity_ranks.keys(),
            effective_start_date__lte=service_date,
        ).filter(
            models.Q(effective_end_date__isnull=True)
            | models.Q(effective_end_date__gte=service_date)
        )

        levels = self._scope_levels(network_id, lob, product_id)
        any_matches = False
        for level_name, match_fn in levels:
            matches = match_fn(qs, network_id, service_date, lob, product_id)
            match_list = list(matches)
            if not match_list:
                continue
            any_matches = True
            contract_id = self._pick_contract_by_entity_rank(
                match_list, entity_ranks, level_name,
            )
            if contract_id is not None:
                return contract_id

        if not any_matches:
            raise ContractResolutionError(
                f'No matching contract for covered entities orgs={org_list} '
                f'network={network_id} lob={lob}',
                is_oon=True,
            )

        raise ContractResolutionError(
            f'No matching contract for covered entities orgs={org_list} '
            f'network={network_id} lob={lob}',
            is_oon=True,
        )

    def _scope_levels(
        self,
        network_id: int | None,
        lob: str | None,
        product_id: int | None,
    ) -> list[tuple[str, Callable]]:
        levels: list[tuple[str, Callable]] = []
        if network_id is not None and product_id is not None and lob is not None:
            levels.append(('product', self._contracts_with_product_scope))
        if network_id is not None and lob is not None:
            levels.append(('lob', self._contracts_with_lob))
        if network_id is not None:
            levels.append(('network', self._contracts_network_only))
        if network_id is None:
            levels.append(('org', lambda qs, *_a, **_k: qs))
        return levels

    @staticmethod
    def _active_contracts_qs(org_id: str, service_date: date) -> models.QuerySet:
        return ProviderContract.objects.filter(
            provider_org_id=org_id,
            effective_start_date__lte=service_date,
        ).filter(
            models.Q(effective_end_date__isnull=True)
            | models.Q(effective_end_date__gte=service_date)
        )

    @staticmethod
    def _normalize_claim_type(claim_type: str | None) -> str | None:
        if not claim_type:
            return None
        return claim_type.strip().upper()

    def _eligible_contract_ids(
        self,
        contract_ids: list[int],
        claim_type: str | None,
    ) -> set[int]:
        """D5.1: filter by ContractArrangement claim_type (null/ALL = any)."""
        if not contract_ids:
            return set()
        normalized = self._normalize_claim_type(claim_type)
        eligible: set[int] = set()
        for cid in contract_ids:
            arrangements = ContractArrangement.objects.filter(contract_id=cid)
            if not arrangements.exists():
                eligible.add(cid)
                continue
            for arr in arrangements:
                arr_type = (arr.claim_type or '').strip().upper() or None
                if arr_type is None or arr_type == 'ALL':
                    eligible.add(cid)
                    break
                if normalized and arr_type == normalized:
                    eligible.add(cid)
                    break
        return eligible

    def _pick_contract(
        self,
        queryset: models.QuerySet,
        specificity_level: str,
        claim_type: str | None = None,
    ) -> int | None:
        contracts = list(queryset)
        if not contracts:
            return None
        if claim_type is not None:
            eligible = self._eligible_contract_ids(
                [c.contract_id for c in contracts], claim_type,
            )
            contracts = [c for c in contracts if c.contract_id in eligible]
        if not contracts:
            return None
        contracts.sort(key=lambda c: (c.resolution_priority, c.contract_id))
        top_priority = contracts[0].resolution_priority
        top_matches = [c for c in contracts if c.resolution_priority == top_priority]
        if len(top_matches) > 1:
            ids = [c.contract_id for c in top_matches]
            raise ContractResolutionAmbiguityError(
                f'Ambiguous contract resolution at {specificity_level} level: '
                f'contract_ids={ids} share resolution_priority={top_priority}',
                specificity_level=specificity_level,
                contract_ids=ids,
            )
        return top_matches[0].contract_id

    @staticmethod
    def _unified_scope_date_filter(service_date: date) -> models.Q:
        """Effective dating for product-scope rows (null dates = always active)."""
        return (
            models.Q(effective_date__isnull=True)
            | models.Q(effective_date__lte=service_date)
        ) & (
            models.Q(termination_date__isnull=True)
            | models.Q(termination_date__gte=service_date)
        )

    def _pick_contract_by_entity_rank(
        self,
        contracts: list[ProviderContract],
        entity_ranks: dict[int, int],
        specificity_level: str,
    ) -> int | None:
        if not contracts:
            return None
        contracts.sort(
            key=lambda c: (
                -entity_ranks.get(c.contract_id, 0),
                c.resolution_priority,
                c.contract_id,
            )
        )
        top_rank = entity_ranks.get(contracts[0].contract_id, 0)
        top_priority = contracts[0].resolution_priority
        top_matches = [
            c for c in contracts
            if entity_ranks.get(c.contract_id, 0) == top_rank
            and c.resolution_priority == top_priority
        ]
        if len(top_matches) > 1:
            ids = [c.contract_id for c in top_matches]
            raise ContractResolutionAmbiguityError(
                f'Ambiguous contract resolution at {specificity_level} level: '
                f'contract_ids={ids} share entity_rank={top_rank} and '
                f'resolution_priority={top_priority}',
                specificity_level=specificity_level,
                contract_ids=ids,
            )
        return top_matches[0].contract_id

    def _entity_ranks_from_covered_entities(
        self,
        *,
        org_list: list[str],
        facility_id: int | None,
        provider_id: int | None,
        service_date: date,
    ) -> dict[int, int]:
        """Map contract_id → best entity-specificity rank for this claim."""
        ranks: dict[int, int] = {}
        org_index = {oid: idx for idx, oid in enumerate(org_list)}
        date_active = (
            models.Q(effective_start_date__isnull=True)
            | models.Q(effective_start_date__lte=service_date)
        ) & (
            models.Q(effective_end_date__isnull=True)
            | models.Q(effective_end_date__gte=service_date)
        )

        ce_qs = ContractCoveredEntity.objects.filter(
            contract__effective_start_date__lte=service_date,
        ).filter(
            models.Q(contract__effective_end_date__isnull=True)
            | models.Q(contract__effective_end_date__gte=service_date)
        ).filter(date_active)

        for ce in ce_qs.select_related('contract'):
            cid = ce.contract_id
            rank = 0

            if ce.entity_type == ContractCoveredEntity.EntityType.ORG:
                if ce.organization_id and ce.organization_id in org_index:
                    rank = RANK_ORG_LEAF - org_index[ce.organization_id]
            elif ce.entity_type == ContractCoveredEntity.EntityType.FACILITY:
                if facility_id and ce.facility_id == facility_id:
                    rank = RANK_FACILITY
            elif ce.entity_type == ContractCoveredEntity.EntityType.PROVIDER:
                if provider_id and ce.provider_id == provider_id:
                    rank = RANK_PROVIDER

            if rank <= 0:
                continue

            if (
                provider_id
                and facility_id
                and self._contract_covers_provider_and_facility(
                    cid, provider_id, facility_id, service_date,
                )
            ):
                rank = max(rank, RANK_PROVIDER_AT_FACILITY)

            ranks[cid] = max(ranks.get(cid, 0), rank)

        # Backfill / test compatibility: provider_org implies ORG coverage only when
        # the contract has no ContractCoveredEntity rows (legacy tests / pre-C3 data).
        for contract in self._active_contracts_for_orgs(org_list, service_date):
            if ContractCoveredEntity.objects.filter(contract_id=contract.contract_id).exists():
                continue
            oid = contract.provider_org_id
            if oid in org_index:
                rank = RANK_ORG_LEAF - org_index[oid]
                ranks[contract.contract_id] = max(
                    ranks.get(contract.contract_id, 0), rank,
                )

        return ranks

    def _active_contracts_for_orgs(
        self, org_list: list[str], service_date: date,
    ) -> models.QuerySet:
        return ProviderContract.objects.filter(
            provider_org_id__in=org_list,
            effective_start_date__lte=service_date,
        ).filter(
            models.Q(effective_end_date__isnull=True)
            | models.Q(effective_end_date__gte=service_date)
        )

    @staticmethod
    def _contract_covers_provider_and_facility(
        contract_id: int,
        provider_id: int,
        facility_id: int,
        service_date: date,
    ) -> bool:
        date_filter = (
            models.Q(effective_start_date__isnull=True)
            | models.Q(effective_start_date__lte=service_date)
        ) & (
            models.Q(effective_end_date__isnull=True)
            | models.Q(effective_end_date__gte=service_date)
        )
        has_provider = ContractCoveredEntity.objects.filter(
            contract_id=contract_id,
            entity_type=ContractCoveredEntity.EntityType.PROVIDER,
            provider_id=provider_id,
        ).filter(date_filter).exists()
        has_facility = ContractCoveredEntity.objects.filter(
            contract_id=contract_id,
            entity_type=ContractCoveredEntity.EntityType.FACILITY,
            facility_id=facility_id,
        ).filter(date_filter).exists()
        return has_provider and has_facility

    def _contracts_with_product_scope(
        self, qs, network_id, service_date, lob, product_id,
    ):
        scoped_ids = ContractScopeUnified.objects.filter(
            product_id=product_id,
            lob_code=lob,
        ).filter(
            self._unified_scope_date_filter(service_date),
        ).values_list('contract_id', flat=True)

        return qs.filter(
            contract_id__in=scoped_ids,
            network__network_id__in=self._network_ids_for(network_id),
        )

    def _contracts_with_lob(self, qs, network_id, service_date, lob, _product_id):
        scoped_ids = ContractScopeUnified.objects.filter(
            lob_code=lob,
            product__isnull=True,
            migration_source=ContractScopeUnified.MigrationSource.PRODUCT_SCOPE,
        ).filter(
            self._unified_scope_date_filter(service_date),
        ).values_list('contract_id', flat=True)

        legacy_scope_ids = ContractScopeUnified.objects.filter(
            lob_code=lob,
            migration_source=ContractScopeUnified.MigrationSource.CONTRACT_SCOPE,
        ).values_list('contract_id', flat=True)

        return qs.filter(
            models.Q(contract_id__in=scoped_ids)
            | models.Q(contract_id__in=legacy_scope_ids)
            | models.Q(line_of_business=lob),
            network__network_id__in=self._network_ids_for(network_id),
        )

    def _contracts_network_only(self, qs, network_id, _service_date, _lob, _product_id):
        network_ids = self._network_ids_for(network_id)
        if not network_ids:
            return ProviderContract.objects.none()
        return qs.filter(network__network_id__in=network_ids)

    def _network_ids_for(self, network_id: int) -> list:
        from products.models import Network

        try:
            net = Network.objects.get(id=network_id)
            if net.legacy_payer_network_id:
                return [net.legacy_payer_network_id]
        except Network.DoesNotExist:
            pass
        return []
