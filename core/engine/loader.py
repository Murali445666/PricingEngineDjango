from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from django.db.models import Q, Case, When, Value, IntegerField
from django.conf import settings

from core.models import (
    PricingRule,
    FeeScheduleRate,
    RefProcedureCode,
    RefModifier,
    RefMpfsRvu,
    RefGeoIndex,
    RefDrg,
    ContractMethodology,
    ContractVersion,
    ContractBaseRate,
    ContractTerm,
    RefAspPricing,
    ProviderContract,
    ContractScope,
    ContractProviderParticipation,
    ContractStopLossRule,
    ContractOutlierRule,
    ContractCarveout,
    ContractCapFloor,
    ContractBlendingRule,
    PerDiemRate,
    ModifierAdjustment,
    ContractFlatRateOverride,
    MPPRDefinition,
    TierMultiplier,
)
from .types import PricingContext, PricingInput, PricingTrace
from .config import ContractPricingConfig
from .exceptions import ContractResolutionError, ContractResolutionTieError


def _tiered_resolution_enabled() -> bool:
    return bool(getattr(settings, 'FEATURE_TIERED_RESOLUTION', False))


def _claim_tier_value_matches_row(claim_val, row_val) -> bool:
    """Claim unset => only wildcard rows (no product/network filter on row). Claim set => row wild or equal."""
    claim_set = claim_val is not None and str(claim_val).strip() != ''
    row_set = row_val is not None and str(row_val).strip() != ''
    if claim_set:
        if not row_set:
            return True
        return str(row_val).strip() == str(claim_val).strip()
    return not row_set


def _log_tier_multiplier_applied(
    trace: Optional[PricingTrace],
    tier_cf: Decimal,
    tier_meta: Dict[str, Any],
    rule: PricingRule,
    input_data: PricingInput,
) -> None:
    if trace is None or not _tiered_resolution_enabled():
        return
    v = getattr(rule, 'version', None)
    tp = getattr(v, 'tier_priority', None) if v is not None else None
    trace.log(
        "TIER_MULTIPLIER",
        f"applied multiplier={tier_cf} source={tier_meta.get('source', '')} "
        f"product_id={getattr(input_data, 'product_id', None)!r} "
        f"network_id={getattr(input_data, 'network_id', None)!r} "
        f"tier_priority={tp}",
    )


def resolve_contract_for_claim(claim_header):
    """
    Phase 8: Resolve a single contract for a claim when claim_header.contract is None.
    Step 1: Filter by provider participation (org or NPI + service_date in range).
    Step 2: Match scopes (line_of_business, specialty, site_of_service, geo; null = wildcard).
    Step 3: Rank by specificity (most matching non-null scope fields), then lowest priority,
            then most recent contract version effective date.
    Returns ProviderContract. Raises ContractResolutionError if no match, ContractResolutionTieError if tie.
    """
    service_date = claim_header.service_date
    provider_org_id = getattr(claim_header, 'provider_org_id', None)
    npi_val = (getattr(claim_header, 'npi', None) or '').strip() or None
    if not provider_org_id and not npi_val:
        raise ContractResolutionError(
            'Claim has no provider_org_id or npi; cannot resolve contract by participation.'
        )

    # Step 1: Participation filter — contracts with matching participation and service_date in range
    part_qs = ContractProviderParticipation.objects.filter(
        effective_start_date__lte=service_date,
    ).filter(
        Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date),
    )
    if provider_org_id and npi_val:
        part_qs = part_qs.filter(Q(organization_id=provider_org_id) | Q(npi=npi_val))
    elif provider_org_id:
        part_qs = part_qs.filter(organization_id=provider_org_id)
    else:
        part_qs = part_qs.filter(npi=npi_val)
    contract_ids = list(part_qs.values_list('contract_id', flat=True).distinct())
    if not contract_ids:
        raise ContractResolutionError('No contract participation matches claim provider and service date.')

    # Claim context for scope matching
    claim_lob = (getattr(claim_header, 'line_of_business', None) or '').strip() or None
    claim_site = (getattr(claim_header, 'site_of_service', None) or '').strip() or None
    claim_geo_id = getattr(claim_header, 'geo_id', None)
    if claim_geo_id is None and getattr(claim_header, 'geo', None):
        claim_geo_id = claim_header.geo_id
    provider_specialty = None
    if getattr(claim_header, 'provider_org', None):
        provider_specialty = getattr(claim_header.provider_org, 'primary_specialty_id', None)

    def scope_matches(scope):
        if scope.line_of_business is not None and (scope.line_of_business or '').strip():
            if (claim_lob or '') != (scope.line_of_business or '').strip():
                return False, 0
        # specialty_code FK to RefSpecialty (to_field=specialty_code)
        scope_spec_code = getattr(scope, 'specialty_code_id', None)
        if scope_spec_code is not None:
            if provider_specialty != scope_spec_code:
                return False, 0
        if scope.site_of_service is not None and (scope.site_of_service or '').strip():
            if (claim_site or '') != (scope.site_of_service or '').strip():
                return False, 0
        if scope.geo_id is not None:
            if claim_geo_id != scope.geo_id:
                return False, 0
        spec = sum([
            1 if (scope.line_of_business or '').strip() else 0,
            1 if scope_spec_code is not None else 0,
            1 if (scope.site_of_service or '').strip() else 0,
            1 if scope.geo_id is not None else 0,
        ])
        return True, spec

    candidates = []
    for contract in ProviderContract.objects.filter(pk__in=contract_ids).prefetch_related('scopes', 'versions'):
        scopes = list(contract.scopes.all())
        if not scopes:
            version = next(
                (v for v in sorted(contract.versions.all(), key=lambda v: v.effective_start_date, reverse=True)
                 if v.effective_start_date <= service_date and (v.effective_end_date is None or v.effective_end_date >= service_date)),
                None
            )
            version_date = version.effective_start_date if version else (contract.effective_start_date or date(1900, 1, 1))
            candidates.append((0, 100, version_date, contract))
            continue
        best_spec = -1
        best_priority = 999999
        for scope in scopes:
            match, spec = scope_matches(scope)
            if match and (spec > best_spec or (spec == best_spec and scope.priority < best_priority)):
                best_spec = spec
                best_priority = scope.priority
        if best_spec >= 0:
            version = next(
                (v for v in sorted(contract.versions.all(), key=lambda v: v.effective_start_date, reverse=True)
                 if v.effective_start_date <= service_date and (v.effective_end_date is None or v.effective_end_date >= service_date)),
                None
            )
            version_date = version.effective_start_date if version else (contract.effective_start_date or date(1900, 1, 1))
            candidates.append((best_spec, best_priority, version_date, contract))

    if not candidates:
        raise ContractResolutionError('No contract scope matches claim dimensions.')

    # Step 3: Rank by (specificity desc, priority asc, version_date desc)
    def rank_key(x):
        spec, pri, vdate, _ = x
        vo = vdate.toordinal() if hasattr(vdate, 'toordinal') else 0
        return (-spec, pri, -vo)
    candidates.sort(key=rank_key)

    top = candidates[0]
    top_rank = (top[0], top[1], top[2])
    ties = [c for c in candidates if (c[0], c[1], c[2]) == top_rank]
    if len(ties) > 1:
        raise ContractResolutionTieError(
            'Multiple contracts tied for claim resolution (same specificity, priority, version date).'
        )
    return top[3]


def resolve_active_contract_version(contract, service_date: date):
    """
    Phase 7: Resolve the active contract version for a given service date.
    Returns ContractVersion or None. When None, engine uses contract-level (version_id null) data only.
    """
    qs = (
        ContractVersion.objects.filter(contract=contract)
        .filter(effective_start_date__lte=service_date)
        .filter(
            Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date)
        )
        .filter(status=ContractVersion.VersionStatus.ACTIVE)
        .order_by('-version_number')
    )
    return qs.first()


def resolve_contract_version(contract_id: int, version_id: int):
    """
    Resolve a specific contract version by contract_id and version_id (for simulation).
    Use this when the payload specifies version_id; do not fall back to active version.
    ContractVersion uses version_id as primary key (no 'id' field).
    Returns ContractVersion. Raises ValueError if not found or version does not belong to contract.
    """
    try:
        return ContractVersion.objects.select_related("contract").get(
            contract_id=contract_id,
            version_id=version_id,
        )
    except ContractVersion.DoesNotExist:
        raise ValueError(
            f"Version {version_id} not found for contract {contract_id}. "
            "Ensure version_id exists and belongs to the given contract."
        )


def build_contract_pricing_config_from_db(contract, version, service_date: date) -> ContractPricingConfig:
    """
    Build an immutable, request-scoped ContractPricingConfig from the database.
    Used when no snapshot is provided. ContractPricingConfig must not be mutated after construction.
    """
    rules_qs = (
        PricingRule.objects.filter(
            contract=contract,
            status=PricingRule.RuleStatus.ACTIVE,
            effective_start_date__lte=service_date,
        )
        .filter(Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date))
        .select_related('contract', 'base_fee_schedule', 'version')
        .prefetch_related('conditions')
    )
    if version is not None:
        rules_qs = rules_qs.filter(Q(version=version) | Q(version__isnull=True))
        rules_qs = rules_qs.annotate(
            _version_first=Case(
                When(version_id=version.pk, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by('_version_first', '-specificity_score')
    else:
        rules_qs = rules_qs.filter(version__isnull=True).order_by('-specificity_score')
    rules = tuple(rules_qs)
    # Debug: verify which rules entered config (e.g. rule 74 with code_group condition)
    rule_ids = [r.rule_id for r in rules]
    print(f"[CONFIG] loaded {len(rules)} rules: rule_ids={rule_ids}")
    for r in rules:
        conds = list(r.conditions.all()) if hasattr(r, 'conditions') else []
        cond_summary = [(c.attribute_name, c.operator, c.attribute_value) for c in conds]
        print(f"[CONFIG] loaded rule_id={r.rule_id}, rule_type={getattr(r, 'rule_type', None)!r}, conditions={cond_summary}")
    # Phase 1: partition rules by stage (rule_type; null/blank -> 'BASE') for resolve_for_stage.
    # Use uppercase keys so resolve_for_stage(stage_key="ADJUSTMENT") matches.
    rules_by_stage = {}
    for r in rules:
        stage_key = ((getattr(r, 'rule_type', None) or 'BASE').strip() or 'BASE').upper()
        rules_by_stage.setdefault(stage_key, []).append(r)
    rules_by_stage = {k: tuple(v) for k, v in rules_by_stage.items()}
    for stage_key, stage_rules in rules_by_stage.items():
        print(f"[CONFIG] rules_by_stage[{stage_key}]: {len(stage_rules)} rules, rule_ids={[r.rule_id for r in stage_rules]}")

    # If rule 74 is missing and we're building for a contract that might have it, explain why (diagnostic)
    if 74 not in rule_ids and contract.pk == 10 and version is not None:
        r74 = PricingRule.objects.filter(rule_id=74).first()
        if r74 is not None:
            v_ok = r74.version_id == version.pk or r74.version_id is None
            print(
                f"[CONFIG] Rule 74 exists but was excluded: contract_id={r74.contract_id}, version_id={r74.version_id} "
                f"(expected version.pk={version.pk}), status={getattr(r74, 'status', None)}, "
                f"effective_start={getattr(r74, 'effective_start_date', None)}, effective_end={getattr(r74, 'effective_end_date', None)}; "
                f"version_match={v_ok}"
            )
        else:
            print("[CONFIG] Rule 74 not found in DB for any contract.")

    methodologies_qs = ContractMethodology.objects.filter(
        contract=contract,
        effective_date__lte=service_date,
    ).filter(
        Q(termination_date__isnull=True) | Q(termination_date__gte=service_date)
    )
    if version is not None:
        methodologies_qs = methodologies_qs.filter(Q(version=version) | Q(version__isnull=True))
    else:
        methodologies_qs = methodologies_qs.filter(version__isnull=True)
    # N+1 ELIMINATED (H1): select_related so methodology.fee_schedule never lazy-loads per line.
    methodologies = tuple(
        methodologies_qs.select_related('fee_schedule').order_by('-priority', '-effective_date')
    )

    stoploss_qs = (
        ContractStopLossRule.objects.filter(contract=contract)
        .filter(effective_start_date__lte=service_date)
        .filter(
            Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date)
        )
        .order_by('-priority')
    )
    if version is not None:
        stoploss_qs = stoploss_qs.filter(Q(version=version) | Q(version__isnull=True))
    else:
        stoploss_qs = stoploss_qs.filter(version__isnull=True)
    stop_loss_rules = tuple(stoploss_qs)

    outlier_qs = (
        ContractOutlierRule.objects.filter(contract=contract)
        .filter(effective_start_date__lte=service_date)
        .filter(
            Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date)
        )
        .order_by('-priority')
    )
    if version is not None:
        outlier_qs = outlier_qs.filter(Q(version=version) | Q(version__isnull=True))
    else:
        outlier_qs = outlier_qs.filter(version__isnull=True)
    outlier_rules = tuple(outlier_qs)

    # N+1 ELIMINATED (H2): preload ContractBaseRate once so load_context never queries it per line.
    base_rates: dict = {}
    if version is not None:
        for cbr in ContractBaseRate.objects.filter(version=version):
            base_rates[cbr.rate_type] = cbr.base_rate

    # Step 7: load carve-outs once per config build (no per-line query).
    carveouts: tuple = ()
    if version is not None:
        carveouts = tuple(
            ContractCarveout.objects.filter(version=version)
            .order_by('code_type', 'code_value')
        )

    # Step 8: load caps/floors once per config build; filter by service_date.
    cap_floors: tuple = ()
    line_cap_floors: tuple = ()
    if version is not None:
        cap_floors_qs = (
            ContractCapFloor.objects.filter(
                version=version,
                effective_start_date__lte=service_date,
            ).filter(
                Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date)
            ).order_by('-priority', 'effective_start_date')
        )
        cap_floors = tuple(cap_floors_qs)
        # Phase G: line-level cap/floors (scope=LINE) for LINE_CAP_FLOOR stage; claim step skips LINE.
        line_cap_floors = tuple(c for c in cap_floors if (getattr(c, 'scope', None) or 'CLAIM').upper() == 'LINE')

    # Step 9: load blending rules once per config build; filter by service_date.
    blending_rules: tuple = ()
    if version is not None:
        blending_rules_qs = (
            ContractBlendingRule.objects.filter(
                version=version,
                effective_start_date__lte=service_date,
            ).filter(
                Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date)
            ).order_by('-priority', 'effective_start_date')
        )
        blending_rules = tuple(blending_rules_qs)

    # Phase F: load MPPR definitions (effective for service_date) with scopes for cross-line phase.
    mppr_definitions: tuple = ()
    if version is not None:
        mppr_qs = (
            MPPRDefinition.objects.filter(
                contract=contract,
                version=version,
                effective_start_date__lte=service_date,
            ).filter(
                Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date)
            ).prefetch_related('scopes')
            .order_by('effective_start_date')
        )
        mppr_definitions = tuple(mppr_qs)

    return ContractPricingConfig(
        contract=contract,
        version=version,
        service_date=service_date,
        rules=rules,
        methodologies=methodologies,
        stop_loss_rules=stop_loss_rules,
        outlier_rules=outlier_rules,
        base_rates=base_rates,
        carveouts=carveouts,
        cap_floors=cap_floors,
        line_cap_floors=line_cap_floors,
        blending_rules=blending_rules,
        rules_by_stage=rules_by_stage,
        mppr_definitions=mppr_definitions,
    )


def build_contract_pricing_config_from_version(version, service_date: date) -> ContractPricingConfig:
    """
    Step 13: Build config for a specific contract version (simulation).
    No resolver lookup; version must be pre-fetched and belong to the contract.
    Uses same loading logic as build_contract_pricing_config_from_db.
    """
    if version is None:
        raise ValueError("version is required for build_contract_pricing_config_from_version")
    contract = version.contract
    return build_contract_pricing_config_from_db(contract, version, service_date)


def resolve_contract_methodology(contract, as_of_date: date, claim_type: Optional[str] = None, version=None):
    """
    Phase 2B: Resolve contract-level methodology for a given date and optional claim_type.
    Phase 7: When version is given, prefer version-scoped methodologies; include contract-level (version null) as fallback.
    Returns the best-matching ContractMethodology or None.
    """
    qs = ContractMethodology.objects.filter(
        contract=contract,
        effective_date__lte=as_of_date,
    ).filter(
        Q(termination_date__isnull=True) | Q(termination_date__gte=as_of_date)
    )
    if version is not None:
        qs = qs.filter(Q(version=version) | Q(version__isnull=True))
    else:
        qs = qs.filter(version__isnull=True)
    if claim_type:
        qs = qs.filter(Q(claim_type__isnull=True) | Q(claim_type='') | Q(claim_type=claim_type))
    # Prefer version-scoped when version given: order so version_id is not null first
    if version is not None:
        qs = qs.annotate(
            _version_first=Case(
                When(version_id=version.pk, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by('_version_first', '-priority', '-effective_date')
    else:
        qs = qs.order_by('-priority', '-effective_date')
    return qs.first()


def _year_for_lookup(fee_schedule):
    """Effective year for RVU/geo lookup: fee_schedule.effective_year or None (caller may use default)."""
    if fee_schedule and getattr(fee_schedule, 'effective_year', None) is not None:
        return fee_schedule.effective_year
    return None


def _quarter_from_date(d: date) -> Optional[str]:
    """Return quarter string e.g. '2024-Q1' for ASP lookup."""
    if d is None:
        return None
    month = d.month
    if month <= 3:
        q = 'Q1'
    elif month <= 6:
        q = 'Q2'
    elif month <= 9:
        q = 'Q3'
    else:
        q = 'Q4'
    return f'{d.year}-{q}'


def _pick_methodology_from_config(methodologies, as_of: date, claim_type: Optional[str] = None):
    """Pick first methodology from config that matches as_of date and optional claim_type."""
    for m in methodologies:
        if m.effective_date > as_of:
            continue
        if getattr(m, 'termination_date', None) is not None and m.termination_date < as_of:
            continue
        if claim_type and getattr(m, 'claim_type', None) and (m.claim_type or '').strip() and m.claim_type != claim_type:
            continue
        return m
    return None


class PricingDataLoader:
    """
    Loads per-line pricing context. Holds a per-execution reference data cache to avoid
    N+1 queries when the same codes / geo / modifiers appear across multiple claim lines.
    Call reset_execution_cache() at the start of each claim pricing execution.
    """

    def __init__(self):
        # Per-execution cache: lives only for one claim pricing run; reset by ClaimOrchestrator.
        self._cache: dict = {}

    def reset_execution_cache(self) -> None:
        """Clear per-execution reference data cache. Called once per claim before the line loop."""
        self._cache = {}

    def _get_rule_multiplier(self, rule: PricingRule, service_date: date) -> Optional[Decimal]:
        """
        Phase B: Return multiplier for rule. When rule.contract_term_id is set, use ContractTerm.multiplier
        if the term is effective for service_date; otherwise use rule.multiplier. Cached per (contract_term_id, service_date).
        """
        contract_term_id = getattr(rule, 'contract_term_id', None)
        if not contract_term_id:
            return rule.multiplier
        cache_key = ('contract_term', contract_term_id, service_date)
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            term = ContractTerm.objects.get(pk=contract_term_id)
            if term.effective_start_date <= service_date and (
                term.effective_end_date is None or term.effective_end_date >= service_date
            ):
                self._cache[cache_key] = term.multiplier
                return term.multiplier
        except ContractTerm.DoesNotExist:
            pass
        self._cache[cache_key] = rule.multiplier
        return rule.multiplier

    def _resolve_multiplier_from_reference(
        self,
        rule: PricingRule,
        methodology: Optional[ContractMethodology],
        service_date: date,
    ) -> Decimal:
        """
        Phase D: Resolve conversion_factor/multiplier only from reference data (ContractTerm).
        When USE_REFERENCE_ONLY_PRICING: rule.contract_term_id else methodology.contract_term_id else 1.0000.
        """
        term_id = getattr(rule, 'contract_term_id', None)
        if not term_id and methodology:
            term_id = getattr(methodology, 'contract_term_id', None)
        if not term_id:
            return Decimal("1.0000")
        cache_key = ('contract_term', term_id, service_date)
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            term = ContractTerm.objects.get(pk=term_id)
            if term.effective_start_date <= service_date and (
                term.effective_end_date is None or term.effective_end_date >= service_date
            ):
                self._cache[cache_key] = term.multiplier
                return term.multiplier
        except ContractTerm.DoesNotExist:
            pass
        self._cache[cache_key] = Decimal("1.0000")
        return Decimal("1.0000")

    def _resolve_flat_rate_from_reference(
        self,
        rule: PricingRule,
        methodology: Optional[ContractMethodology],
        service_date: date,
        procedure_code: str,
        has_fee_schedule: bool,
    ) -> Optional[Decimal]:
        """
        Phase D: Resolve flat_rate only from reference data. Prefer: rule.per_diem_rate_id (PerDiemRate),
        rule.flat_rate_override_id (ContractFlatRateOverride), fee_schedule + FeeScheduleRate (handled elsewhere),
        methodology default. Never read rule.flat_rate when USE_REFERENCE_ONLY_PRICING.
        """
        per_diem_id = getattr(rule, 'per_diem_rate_id', None)
        if per_diem_id:
            cache_key = ('per_diem', per_diem_id, service_date)
            if cache_key in self._cache:
                return self._cache[cache_key]
            try:
                pd = PerDiemRate.objects.get(pk=per_diem_id)
                if pd.effective_start_date <= service_date and (
                    pd.effective_end_date is None or pd.effective_end_date >= service_date
                ):
                    self._cache[cache_key] = pd.rate_amount
                    return pd.rate_amount
            except PerDiemRate.DoesNotExist:
                pass
            self._cache[cache_key] = None
        flat_ov_id = getattr(rule, 'flat_rate_override_id', None)
        if flat_ov_id:
            cache_key = ('flat_override', flat_ov_id, service_date, procedure_code or '')
            if cache_key in self._cache:
                return self._cache[cache_key]
            try:
                ov = ContractFlatRateOverride.objects.get(pk=flat_ov_id)
                if ov.effective_start_date <= service_date and (
                    ov.effective_end_date is None or ov.effective_end_date >= service_date
                ):
                    if ov.procedure_code in (None, '', procedure_code):
                        self._cache[cache_key] = ov.rate_amount
                        return ov.rate_amount
            except ContractFlatRateOverride.DoesNotExist:
                pass
            self._cache[cache_key] = None
        # No reference flat rate; fee schedule rate is applied later in load_context if has_fee_schedule
        return None

    def _resolve_tier_multiplier(
        self,
        contract: ProviderContract,
        version,
        input_data: PricingInput,
        as_of: date,
    ) -> Tuple[Optional[Decimal], Dict[str, Any]]:
        """Pick best TierMultiplier for contract/version/DOS and optional product/network on input."""
        if not _tiered_resolution_enabled():
            return None, {}
        product_id = getattr(input_data, 'product_id', None)
        network_id = getattr(input_data, 'network_id', None)
        qs = TierMultiplier.objects.filter(
            contract=contract,
            effective_start_date__lte=as_of,
        ).filter(
            Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=as_of)
        )
        if version is not None:
            qs = qs.filter(Q(version__isnull=True) | Q(version_id=version.pk))
        rows = list(qs)
        candidates = [
            r for r in rows
            if _claim_tier_value_matches_row(product_id, r.product_id)
            and _claim_tier_value_matches_row(network_id, r.network_id)
        ]
        if not candidates:
            return None, {}

        def specificity_key(r: TierMultiplier) -> tuple:
            score = 0
            if product_id and str(product_id).strip() and r.product_id and str(r.product_id).strip() == str(product_id).strip():
                score += 4
            elif not (r.product_id and str(r.product_id).strip()):
                score += 1
            if network_id and str(network_id).strip() and r.network_id and str(r.network_id).strip() == str(network_id).strip():
                score += 4
            elif not (r.network_id and str(r.network_id).strip()):
                score += 1
            vbonus = 0
            if version is not None:
                if r.version_id == version.pk:
                    vbonus = 2
                elif r.version_id is None:
                    vbonus = 1
            return (score, vbonus, r.effective_start_date)

        best = max(candidates, key=specificity_key)
        meta = {'source': f'TierMultiplier:{best.pk}', 'tier_multiplier_id': best.pk}
        return best.multiplier, meta

    def load_context(
        self,
        input_data: PricingInput,
        rule: PricingRule,
        version=None,
        config: Optional[ContractPricingConfig] = None,
        trace: Optional[PricingTrace] = None,
    ):
        # Phase 2B: Effective methodology — if rule.methodology_code set, override; else inherit from contract (or version)
        as_of = input_data.service_date or date.today()
        use_reference_only = getattr(settings, 'USE_REFERENCE_ONLY_PRICING', False)
        tier_cf: Optional[Decimal] = None
        tier_meta: Dict[str, Any] = {}
        if _tiered_resolution_enabled():
            tier_cf, tier_meta = self._resolve_tier_multiplier(
                rule.contract, version, input_data, as_of,
            )
        methodology = None
        if rule.methodology_code and str(rule.methodology_code).strip():
            effective_methodology = rule.methodology_code.strip()
            fs = rule.base_fee_schedule
            if use_reference_only:
                # RBRVS / percent-of-billed: always honor rule (and ContractTerm via _get_rule_multiplier);
                # reference-only default 1.0 would drop rule.multiplier when no contract_term_id.
                if effective_methodology in (
                    'RBRVS', 'ANESTHESIA', 'PCT_BILLED', 'PERCENT_BILLED',
                ):
                    conversion_factor = self._get_rule_multiplier(rule, as_of)
                else:
                    conversion_factor = self._resolve_multiplier_from_reference(rule, None, as_of)
                flat_rate = self._resolve_flat_rate_from_reference(
                    rule, None, as_of, input_data.procedure_code or '',
                    has_fee_schedule=bool(getattr(rule, 'base_fee_schedule_id', None)),
                )
            else:
                conversion_factor = self._get_rule_multiplier(rule, as_of)
                flat_rate = rule.flat_rate
        else:
            if config is not None and config.methodologies:
                methodology = _pick_methodology_from_config(
                    config.methodologies, as_of, input_data.claim_type
                )
            else:
                methodology = resolve_contract_methodology(
                    rule.contract, as_of, input_data.claim_type, version=version
                )
            if methodology:
                effective_methodology = methodology.methodology_type
                fs = methodology.fee_schedule
                if use_reference_only:
                    if effective_methodology in (
                        'RBRVS', 'ANESTHESIA', 'PCT_BILLED', 'PERCENT_BILLED',
                    ):
                        conversion_factor = self._get_rule_multiplier(rule, as_of)
                    else:
                        conversion_factor = self._resolve_multiplier_from_reference(rule, methodology, as_of)
                    flat_rate = self._resolve_flat_rate_from_reference(
                        rule, methodology, as_of, input_data.procedure_code or '',
                        has_fee_schedule=bool(fs),
                    )
                else:
                    conversion_factor = methodology.conversion_factor
                    flat_rate = rule.flat_rate
            else:
                effective_methodology = ''
                fs = None
                if use_reference_only:
                    conversion_factor = self._resolve_multiplier_from_reference(rule, None, as_of)
                    flat_rate = self._resolve_flat_rate_from_reference(
                        rule, None, as_of, input_data.procedure_code or '', has_fee_schedule=False
                    )
                else:
                    conversion_factor = None
                    flat_rate = rule.flat_rate

        # Phase 7: Version-scoped DRG/APC base rate from contract_base_rates when available.
        # N+1 ELIMINATED (H2): use config.base_rates preloaded once; fall back to DB only when no config.
        if version and effective_methodology in ('DRG', 'APC'):
            if config is not None and effective_methodology in config.base_rates:
                base_rate_val = config.base_rates[effective_methodology]
                if effective_methodology == 'DRG':
                    flat_rate = base_rate_val
                else:
                    conversion_factor = base_rate_val
            else:
                try:
                    base_rate_row = ContractBaseRate.objects.filter(
                        version=version, rate_type=effective_methodology
                    ).first()
                    if base_rate_row:
                        if effective_methodology == 'DRG':
                            flat_rate = base_rate_row.base_rate
                        else:
                            conversion_factor = base_rate_row.base_rate
                except Exception:
                    pass

        # 1. Initialize Context with Explicit Metadata
        context = PricingContext(
            input_data=input_data,
            contract_id=str(rule.contract.pk),
            rule_id=rule.rule_id,
            rule_name=rule.rule_name or '',
            methodology_code=effective_methodology,
        )

        # 2. Populate Methodology-Specific Fields
        if effective_methodology == 'RBRVS':
            cm = conversion_factor
            rm = self._get_rule_multiplier(rule, as_of)
            # Prefer methodology CF, then rule/term multiplier, then tier default (14a), then 1.
            if cm is not None:
                context.conversion_factor = cm
            elif rm is not None:
                context.conversion_factor = rm
            elif tier_cf is not None and _tiered_resolution_enabled():
                context.conversion_factor = tier_cf
                _log_tier_multiplier_applied(trace, tier_cf, tier_meta, rule, input_data)
            else:
                context.conversion_factor = Decimal('1')
        elif effective_methodology == 'ANESTHESIA':
            cm = conversion_factor
            rm = self._get_rule_multiplier(rule, as_of)
            if cm is not None:
                context.conversion_factor = cm
            elif rm is not None:
                context.conversion_factor = rm
            elif tier_cf is not None and _tiered_resolution_enabled():
                context.conversion_factor = tier_cf
                _log_tier_multiplier_applied(trace, tier_cf, tier_meta, rule, input_data)
            else:
                context.conversion_factor = Decimal('1')
        elif effective_methodology in ('OPPS', 'APC'):
            cf = conversion_factor
            if cf is None and tier_cf is not None and _tiered_resolution_enabled():
                cf = tier_cf
                _log_tier_multiplier_applied(trace, tier_cf, tier_meta, rule, input_data)
            context.conversion_factor = cf
        elif effective_methodology in ['FLAT_RATE', 'PER_DIEM']:
            # Reference-only resolution skips rule.flat_rate; fall back when no PerDiem/override row exists.
            fr = flat_rate if flat_rate is not None else rule.flat_rate
            context.flat_rate = fr
            if effective_methodology == 'FLAT_RATE' and getattr(rule, 'base_fee_schedule_id', None):
                context.base_fee_schedule_id = rule.base_fee_schedule_id
        elif effective_methodology in ('PERCENT_BILLED', 'PCT_BILLED'):
            po = getattr(rule, 'percent_of_billed', None)
            if po is not None:
                context.percent_of_billed = po
            else:
                m = self._get_rule_multiplier(rule, as_of)
                # Step 14a: tier is default percent when no ContractTerm and rule still has schema default 1.0
                if (
                    not getattr(rule, 'contract_term_id', None)
                    and tier_cf is not None
                    and _tiered_resolution_enabled()
                    and m is not None
                    and m == Decimal('1.0000')
                ):
                    m = tier_cf
                    _log_tier_multiplier_applied(trace, tier_cf, tier_meta, rule, input_data)
                context.percent_of_billed = m if m is not None else Decimal('1')
        elif effective_methodology == 'DRG':
            context.flat_rate = flat_rate

        # 3. Stop Loss
        if rule.rule_type == 'STOP_LOSS':
            context.is_stop_loss = True
            context.stop_loss_threshold = rule.flat_rate
            context.stop_loss_multiplier = rule.multiplier

        # 4. Fetch External Data (Rates, Weights, Modifiers)
        year = _year_for_lookup(fs) if fs else None

        # A. Fee Schedule Rate (Phase 5: filter by service_date when rate has effective dates or year)
        # N+1 ELIMINATED (H3): cache per (fs_id, code, svc_date) — same code on multiple lines hits DB once.
        if fs:
            svc_date = input_data.service_date or date.today()
            _fsr_key = ('fsr', fs.pk, input_data.procedure_code, svc_date)
            if _fsr_key in self._cache:
                _cached_rate = self._cache[_fsr_key]
                if _cached_rate is not None:
                    context.base_rate = _cached_rate
            else:
                try:
                    qs = FeeScheduleRate.objects.filter(
                        fee_schedule=fs,
                        code_id=input_data.procedure_code,
                    )
                    # When rate has effective_start_date/effective_end_date, require service_date in range
                    qs = qs.filter(
                        Q(effective_start_date__isnull=True) | Q(effective_start_date__lte=svc_date)
                    ).filter(
                        Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=svc_date)
                    )
                    rate_obj = qs.order_by('-year').first()
                    if rate_obj is None:
                        # Fallback: unrestricted (any rate for this schedule/code)
                        rate_obj = FeeScheduleRate.objects.filter(
                            fee_schedule=fs,
                            code_id=input_data.procedure_code,
                        ).first()
                    rate_amount = rate_obj.rate_amount if rate_obj is not None else None
                    self._cache[_fsr_key] = rate_amount
                    if rate_amount is not None:
                        context.base_rate = rate_amount
                except Exception:
                    context.base_rate = None
                    self._cache[_fsr_key] = None

        # A2. RBRVS: optionally prefer RefMpfsRvu for (code, year) when available.
        # N+1 ELIMINATED (H4): cache per (code, year) — same code on multiple lines hits DB once.
        if effective_methodology == 'RBRVS' and year is not None:
            _rvu_key = ('rvu', input_data.procedure_code, year)
            if _rvu_key in self._cache:
                _rvu_data = self._cache[_rvu_key]
                if _rvu_data is not None:
                    context.work_rvu, context.pe_rvu, context.mp_rvu = _rvu_data
            else:
                try:
                    rvu = RefMpfsRvu.objects.get(
                        code=input_data.procedure_code,
                        year=year,
                    )
                    _rvu_data = (rvu.work_rvu, rvu.pe_rvu, rvu.mp_rvu)
                    self._cache[_rvu_key] = _rvu_data
                    context.work_rvu = rvu.work_rvu
                    context.pe_rvu = rvu.pe_rvu
                    context.mp_rvu = rvu.mp_rvu
                except RefMpfsRvu.DoesNotExist:
                    self._cache[_rvu_key] = None

        # A3. GPCI: when fee schedule has locality (geo), load GPCI from RefGeoIndex.
        # N+1 ELIMINATED (H5): cache per geo_id — same locality used on many lines hits DB once.
        if fs and getattr(fs, 'geo_id', None) is not None:
            _geo_key = ('geo', fs.geo_id)
            if _geo_key in self._cache:
                _geo_data = self._cache[_geo_key]
                if _geo_data is not None:
                    _gw, _gpe, _gmp = _geo_data
                    if _gw is not None:
                        context.gpci_work = _gw
                    if _gpe is not None:
                        context.gpci_pe = _gpe
                    if _gmp is not None:
                        context.gpci_mp = _gmp
            else:
                try:
                    geo = RefGeoIndex.objects.get(pk=fs.geo_id)
                    _geo_data = (geo.gpci_work, geo.gpci_pe, geo.gpci_mp)
                    self._cache[_geo_key] = _geo_data
                    if geo.gpci_work is not None:
                        context.gpci_work = geo.gpci_work
                    if geo.gpci_pe is not None:
                        context.gpci_pe = geo.gpci_pe
                    if geo.gpci_mp is not None:
                        context.gpci_mp = geo.gpci_mp
                except RefGeoIndex.DoesNotExist:
                    self._cache[_geo_key] = None

        # B. DRG Weight (Phase 2: try RefDrg first, fall back to RefProcedureCode.work_rvu).
        # N+1 ELIMINATED (H6): cache per drg_code — same DRG across multiple lines hits DB once.
        if effective_methodology == 'DRG':
            _drg_key = ('drg', input_data.procedure_code)
            if _drg_key in self._cache:
                context.drg_weight = self._cache[_drg_key]
            else:
                try:
                    ref_drg = RefDrg.objects.get(drg_code=input_data.procedure_code)
                    context.drg_weight = ref_drg.relative_weight
                    self._cache[_drg_key] = ref_drg.relative_weight
                except RefDrg.DoesNotExist:
                    try:
                        ref = RefProcedureCode.objects.get(code_id=input_data.procedure_code)
                        context.drg_weight = ref.work_rvu
                        self._cache[_drg_key] = ref.work_rvu
                    except RefProcedureCode.DoesNotExist:
                        context.drg_weight = None
                        self._cache[_drg_key] = None

        # C. Modifiers (RefModifier base; Phase D: contract/version ModifierAdjustment overrides).
        # N+1 ELIMINATED (H7): cache each modifier_code; only fetch codes not yet in cache.
        if input_data.modifiers:
            uncached_codes = []
            for mc in input_data.modifiers:
                _mod_key = ('mod', mc)
                cached = self._cache.get(_mod_key)
                if cached is not None:
                    context.modifier_adjustments[mc] = cached
                else:
                    # Missing key or prior negative cache (None) — (re)query RefModifier.
                    uncached_codes.append(mc)
            if uncached_codes:
                for m in RefModifier.objects.filter(modifier_code__in=uncached_codes):
                    context.modifier_adjustments[m.modifier_code] = m.percentage_adjustment
                    self._cache[('mod', m.modifier_code)] = m.percentage_adjustment
                # Mark codes not found in DB so we don't query them again
                for mc in uncached_codes:
                    if ('mod', mc) not in self._cache:
                        self._cache[('mod', mc)] = None
        # Phase D: overlay contract/version modifier adjustments (override RefModifier when same code).
        _mod_adj_key = ('mod_adj', rule.contract_id, getattr(version, 'pk', None), as_of)
        if _mod_adj_key not in self._cache:
            qs = ModifierAdjustment.objects.filter(
                contract=rule.contract,
                effective_start_date__lte=as_of,
            ).filter(
                Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=as_of)
            )
            if version is not None:
                qs = qs.filter(Q(version=version) | Q(version__isnull=True))
            else:
                qs = qs.filter(version__isnull=True)
            overrides = {m.modifier_code: m.adjustment_value for m in qs}
            self._cache[_mod_adj_key] = overrides
        for mc, val in self._cache[_mod_adj_key].items():
            context.modifier_adjustments[mc] = val

        # D. Phase 3: Optional ASP lookup for drug methodology (when DRUG/ASP strategy is implemented).
        # N+1 ELIMINATED (H8): cache per (hcpcs_code, quarter) — same drug repeated across lines hits DB once.
        if effective_methodology in ('DRUG', 'ASP'):
            _quarter = _quarter_from_date(as_of)
            if _quarter:
                _asp_key = ('asp', input_data.procedure_code, _quarter)
                if _asp_key in self._cache:
                    _asp_data = self._cache[_asp_key]
                    if _asp_data is not None:
                        context.asp_price, context.asp_payment_limit = _asp_data
                else:
                    try:
                        asp_row = RefAspPricing.objects.get(
                            hcpcs_code=input_data.procedure_code,
                            quarter=_quarter,
                        )
                        _asp_data = (asp_row.asp, getattr(asp_row, 'payment_limit', None))
                        self._cache[_asp_key] = _asp_data
                        context.asp_price = asp_row.asp
                        context.asp_payment_limit = _asp_data[1]
                    except RefAspPricing.DoesNotExist:
                        self._cache[_asp_key] = None

        return context