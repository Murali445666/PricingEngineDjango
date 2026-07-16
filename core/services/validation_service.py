"""
Step 10: Contract Conflict Detection and Validation Service.

CRITICAL: This service is for pre-save and explicit validation ONLY.
Never import or call from ClaimOrchestrator, LineOrchestrator, or any pricing path.

Conflict types detected:
  SCOPE_OVERLAP          – ContractScope dimensions duplicated within a contract.
  PARTICIPATION_OVERLAP  – Provider participation date ranges overlap within a contract.
  METHODOLOGY_COLLISION  – Same methodology_type with overlapping effective dates in same version.
  CARVEOUT_OVERLAP       – Same code_type/code_value appears more than once in same version.
  BLENDING_CYCLE         – Blending rules form a directed cycle (A→B→A or longer).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Dict, FrozenSet, List, Optional

# Sentinel for open-ended effective dates
_MAX_DATE = date(9999, 12, 31)

# Canonical claim_type values on PricingRule (lowercase; NULL = wildcard).
_CANONICAL_RULE_CLAIM_TYPES = frozenset({'professional', 'institutional'})


def _evaluable_rule_condition_attributes() -> FrozenSet[str]:
    """
    Attribute names PricingRuleCondition may use and the engine can evaluate.

    Source of truth:
      - core/engine/resolver.py::_matches_with_reason (generic getattr / context.get,
        plus special branches for code, code_group, revenue_code)
      - core/engine/conditions.py::build_line_context (context dict keys)
      - core/engine/types.py::PricingInput (request fields via getattr)
    """
    from dataclasses import fields as dc_fields

    from core.engine.types import PricingInput

    from_context = frozenset({
        'procedure_code', 'billed_amount', 'units', 'claim_type', 'modifiers_count',
        'revenue_code', 'base_allowed_amount', 'current_allowed_amount', 'provider_id',
    })
    from_request = frozenset(f.name for f in dc_fields(PricingInput))
    resolver_aliases = frozenset({'code'})  # mapped to procedure_code in resolver
    resolver_special = frozenset({'code_group'})  # group membership branch in resolver
    return from_context | from_request | resolver_aliases | resolver_special


def _normalize_condition_attribute(attribute_name: str) -> str:
    """Map condition attribute_name to the resolver lookup key."""
    attr = (attribute_name or '').strip()
    if attr == 'code':
        return 'procedure_code'
    if attr.lower() == 'code_group':
        return 'code_group'
    return attr


def _procedure_code_from_rule(rule) -> Optional[str]:
    """Extract EQ-matched procedure code from rule conditions, if present."""
    for cond in rule.conditions.all():
        if cond.attribute_name in ('code', 'procedure_code'):
            op = (getattr(cond, 'operator', None) or 'EQ').strip().upper() or 'EQ'
            if op == 'EQ':
                val = (cond.attribute_value or '').strip()
                if val:
                    return val
    return None

# Step 12d: max contracts per bulk validation request (API enforces the same cap).
BULK_VALIDATE_MAX_CONTRACT_IDS = 100


# ---------------------------------------------------------------------------
# ConflictError
# ---------------------------------------------------------------------------

@dataclass
class ConflictError:
    """
    A single detected conflict. severity is either 'ERROR' or 'WARNING'.
    affected_objects is a list of dicts describing the objects involved.
    """
    conflict_type: str
    severity: str  # ERROR, WARNING
    message: str
    affected_objects: List[Dict[str, Any]] = field(default_factory=list)
    suggested_action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "message": self.message,
            "affected_objects": self.affected_objects,
            "suggested_action": self.suggested_action,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ranges_overlap(s1: date, e1: Optional[date], s2: date, e2: Optional[date]) -> bool:
    """True when two inclusive date ranges overlap. None end = open-ended."""
    _e1 = e1 if e1 is not None else _MAX_DATE
    _e2 = e2 if e2 is not None else _MAX_DATE
    return s1 <= _e2 and s2 <= _e1


# ---------------------------------------------------------------------------
# ValidationService
# ---------------------------------------------------------------------------

class ValidationService:
    """
    Detects configuration conflicts across a contract and its versions.

    Public API:
      validate_contract(contract_id)         – full validation; returns List[ConflictError]
      save_validation_results(contract, conflicts) – persist results to ValidationResult table
      check_carveout_duplicate(carveout)     – lightweight check for a single carveout save
      check_methodology_collision(meth)      – lightweight check for a single methodology save
      check_blending_cycle_for_rule(rule)    – lightweight check for a single blending rule save

    None of these are called from the pricing path.
    """

    # ------------------------------------------------------------------
    # Full contract validation
    # ------------------------------------------------------------------

    @classmethod
    def validate_contract(cls, contract_id: int) -> List[ConflictError]:
        """
        Load contract + all versions and run all conflict checks.
        Returns a flat list of ConflictError (errors first, then warnings).
        """
        from core.models import ProviderContract, ContractVersion
        try:
            contract = ProviderContract.objects.get(pk=contract_id)
        except ProviderContract.DoesNotExist:
            return [ConflictError(
                conflict_type="NOT_FOUND",
                severity="ERROR",
                message=f"Contract {contract_id} not found.",
            )]

        versions = list(ContractVersion.objects.filter(contract=contract))

        conflicts: List[ConflictError] = []
        conflicts.extend(cls._check_scope_overlaps(contract))
        conflicts.extend(cls._check_participation_overlaps(contract))
        conflicts.extend(cls._check_methodology_collisions(contract, versions))
        conflicts.extend(cls._check_carveout_overlaps(versions))
        conflicts.extend(cls._check_blending_cycles(versions))
        conflicts.extend(cls._check_unreachable_rule_conditions(contract))
        conflicts.extend(cls._check_ambiguous_pricing_rules(contract, versions))
        conflicts.extend(cls._check_non_canonical_rule_claim_types(contract))
        conflicts.extend(cls._check_pointless_carveouts(contract, versions))

        # Errors before warnings, then by conflict_type for deterministic ordering
        conflicts.sort(key=lambda c: (0 if c.severity == "ERROR" else 1, c.conflict_type))
        return conflicts

    @classmethod
    def bulk_validate(
        cls,
        contract_ids: List[int],
        *,
        persist: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Step 12d: run validate_contract for each id. One failure does not abort others;
        exceptions become a row with ``errors`` set. Optionally persist results when
        ``persist`` is True (same semantics as POST /api/validate-contract/<id>/?save=1).
        """
        from core.models import ProviderContract

        results: List[Dict[str, Any]] = []
        for cid in contract_ids:
            try:
                conflicts = cls.validate_contract(cid)
            except Exception as exc:  # pragma: no cover — defensive; validate_contract rarely raises
                results.append({
                    "contract_id": cid,
                    "error_count": 0,
                    "warning_count": 0,
                    "conflicts": [],
                    "errors": str(exc),
                })
                continue
            if persist:
                try:
                    contract = ProviderContract.objects.get(pk=cid)
                    cls.save_validation_results(contract, conflicts)
                except ProviderContract.DoesNotExist:
                    pass
            error_count = sum(1 for c in conflicts if c.severity == "ERROR")
            warning_count = sum(1 for c in conflicts if c.severity == "WARNING")
            results.append({
                "contract_id": cid,
                "error_count": error_count,
                "warning_count": warning_count,
                "conflicts": [c.to_dict() for c in conflicts],
            })
        return results

    @classmethod
    def save_validation_results(cls, contract, conflicts: List[ConflictError]) -> None:
        """
        Persist validation results to ValidationResult table.
        Clears previous unresolved results for the contract first.
        """
        from core.models import ValidationResult
        ValidationResult.objects.filter(contract=contract, resolved=False).delete()
        for c in conflicts:
            ValidationResult.objects.create(
                contract=contract,
                conflict_type=c.conflict_type,
                severity=c.severity,
                message=c.message,
                affected_objects=c.affected_objects,
                suggested_action=c.suggested_action,
            )

    # ------------------------------------------------------------------
    # Lightweight per-instance checks (called from model clean())
    # ------------------------------------------------------------------

    @classmethod
    def check_carveout_duplicate(cls, carveout) -> List[ConflictError]:
        """
        Detect carve-out duplicate for a single ContractCarveout being saved.
        Raises if same (version, code_type, code_value) already exists.
        """
        if not carveout.version_id:
            return []
        from core.models import ContractCarveout
        qs = ContractCarveout.objects.filter(
            version_id=carveout.version_id,
            code_type=carveout.code_type,
            code_value=carveout.code_value,
        )
        if carveout.pk:
            qs = qs.exclude(pk=carveout.pk)
        if not qs.exists():
            return []
        existing = list(qs)
        return [ConflictError(
            conflict_type="CARVEOUT_OVERLAP",
            severity="ERROR",
            message=(
                f"A carve-out rule for code_type='{carveout.code_type}', "
                f"code_value='{carveout.code_value}' already exists in "
                f"version {carveout.version_id}."
            ),
            affected_objects=[
                {"type": "ContractCarveout", "id": c.pk, "methodology": c.carveout_methodology}
                for c in existing
            ],
            suggested_action="Remove the existing rule or use a different code value.",
        )]

    @classmethod
    def check_methodology_collision(cls, methodology) -> List[ConflictError]:
        """
        Detect date-range overlap for a single ContractMethodology being saved.
        """
        from core.models import ContractMethodology
        qs = ContractMethodology.objects.filter(
            contract_id=methodology.contract_id,
            methodology_type=methodology.methodology_type,
        )
        if methodology.version_id is None:
            qs = qs.filter(version__isnull=True)
        else:
            qs = qs.filter(version_id=methodology.version_id)
        if methodology.pk:
            qs = qs.exclude(pk=methodology.pk)

        errors = []
        for other in qs:
            if _ranges_overlap(
                methodology.effective_date, methodology.termination_date,
                other.effective_date, other.termination_date,
            ):
                errors.append(ConflictError(
                    conflict_type="METHODOLOGY_COLLISION",
                    severity="ERROR",
                    message=(
                        f"Methodology {other.pk} (type={methodology.methodology_type}) "
                        f"overlaps date range "
                        f"[{methodology.effective_date}, {methodology.termination_date}]."
                    ),
                    affected_objects=[{"type": "ContractMethodology", "id": other.pk}],
                    suggested_action="Adjust termination_date to avoid overlap.",
                ))
        return errors

    @classmethod
    def check_blending_cycle_for_rule(cls, rule) -> List[ConflictError]:
        """
        Detect whether adding/editing this blending rule creates a cycle.
        """
        if not rule.version_id:
            return []
        from core.models import ContractBlendingRule
        existing = list(ContractBlendingRule.objects.filter(version_id=rule.version_id))
        if rule.pk:
            existing = [r for r in existing if r.pk != rule.pk]
        test_rules = existing + [rule]
        cycle = cls._detect_blending_cycle(test_rules)
        if cycle is None:
            return []
        return [ConflictError(
            conflict_type="BLENDING_CYCLE",
            severity="ERROR",
            message=(
                f"Adding blending rule (primary={rule.primary_methodology}, "
                f"secondary={rule.secondary_methodology}) creates a cycle: "
                f"{' → '.join(cycle)}"
            ),
            affected_objects=[{
                "type": "ContractBlendingRule",
                "primary": rule.primary_methodology,
                "secondary": rule.secondary_methodology,
            }],
            suggested_action="Choose a different secondary_methodology to break the cycle.",
        )]

    # ------------------------------------------------------------------
    # Full-scope sub-checks
    # ------------------------------------------------------------------

    @classmethod
    def _check_scope_overlaps(cls, contract) -> List[ConflictError]:
        """
        Detect ContractScope records with identical dimensions within the same contract.
        ERROR: same dimensions AND same priority (ambiguous resolution).
        WARNING: same dimensions, different priorities (suspicious but deterministic).
        """
        from core.models import ContractScope
        scopes = list(ContractScope.objects.filter(contract=contract))

        dim_groups: Dict[tuple, list] = defaultdict(list)
        for s in scopes:
            key = (
                (s.line_of_business or "").strip() or None,
                s.specialty_code_id,
                (s.site_of_service or "").strip() or None,
                s.geo_id,
            )
            dim_groups[key].append(s)

        errors: List[ConflictError] = []
        for key, group in dim_groups.items():
            if len(group) < 2:
                continue
            priority_groups: Dict[int, list] = defaultdict(list)
            for s in group:
                priority_groups[s.priority].append(s)

            for prio, pgroup in priority_groups.items():
                if len(pgroup) > 1:
                    errors.append(ConflictError(
                        conflict_type="SCOPE_OVERLAP",
                        severity="ERROR",
                        message=(
                            f"Contract {contract.pk}: {len(pgroup)} scopes share identical "
                            f"dimensions and priority {prio}. Resolution is ambiguous."
                        ),
                        affected_objects=[
                            {"type": "ContractScope", "id": s.pk, "priority": s.priority}
                            for s in pgroup
                        ],
                        suggested_action="Remove duplicate scopes or assign distinct priorities.",
                    ))

            # Same dims, different priorities — suspicious but not an error
            unique_priorities = len(set(s.priority for s in group))
            has_same_priority_error = any(len(pg) > 1 for pg in priority_groups.values())
            if unique_priorities > 1 and not has_same_priority_error:
                errors.append(ConflictError(
                    conflict_type="SCOPE_OVERLAP",
                    severity="WARNING",
                    message=(
                        f"Contract {contract.pk}: {len(group)} scopes share identical "
                        f"dimensions with different priorities. Verify intended precedence."
                    ),
                    affected_objects=[
                        {"type": "ContractScope", "id": s.pk, "priority": s.priority}
                        for s in group
                    ],
                    suggested_action="Confirm scope priority ordering is intentional.",
                ))
        return errors

    @classmethod
    def _check_participation_overlaps(cls, contract) -> List[ConflictError]:
        """
        Detect ContractProviderParticipation records for same provider/NPI
        with overlapping date ranges in the same contract.
        """
        from core.models import ContractProviderParticipation
        parts = list(ContractProviderParticipation.objects.filter(contract=contract))

        groups: Dict[tuple, list] = defaultdict(list)
        for p in parts:
            key = (p.organization_id, (p.npi or "").strip() or None)
            groups[key].append(p)

        errors: List[ConflictError] = []
        for key, group in groups.items():
            if len(group) < 2:
                continue
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    if _ranges_overlap(
                        a.effective_start_date, a.effective_end_date,
                        b.effective_start_date, b.effective_end_date,
                    ):
                        errors.append(ConflictError(
                            conflict_type="PARTICIPATION_OVERLAP",
                            severity="ERROR",
                            message=(
                                f"Contract {contract.pk}: Participations {a.pk} and {b.pk} "
                                f"for org={key[0]} npi={key[1]} have overlapping date ranges."
                            ),
                            affected_objects=[
                                {
                                    "type": "ContractProviderParticipation",
                                    "id": a.pk,
                                    "start": str(a.effective_start_date),
                                    "end": str(a.effective_end_date),
                                },
                                {
                                    "type": "ContractProviderParticipation",
                                    "id": b.pk,
                                    "start": str(b.effective_start_date),
                                    "end": str(b.effective_end_date),
                                },
                            ],
                            suggested_action="Adjust date ranges so they do not overlap.",
                        ))
        return errors

    @classmethod
    def _check_methodology_collisions(cls, contract, versions=None) -> List[ConflictError]:
        """
        Detect ContractMethodology records sharing the same type with overlapping date ranges
        within the same (contract, version, claim_type) bucket.
        """
        from core.models import ContractMethodology
        methodologies = list(ContractMethodology.objects.filter(contract=contract))

        groups: Dict[tuple, list] = defaultdict(list)
        for m in methodologies:
            key = (m.version_id, m.methodology_type, (m.claim_type or "").strip() or None)
            groups[key].append(m)

        errors: List[ConflictError] = []
        for key, group in groups.items():
            if len(group) < 2:
                continue
            version_str = f"version_id={key[0]}" if key[0] else "contract-level (no version)"
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    if _ranges_overlap(
                        a.effective_date, a.termination_date,
                        b.effective_date, b.termination_date,
                    ):
                        errors.append(ConflictError(
                            conflict_type="METHODOLOGY_COLLISION",
                            severity="ERROR",
                            message=(
                                f"Contract {contract.pk} ({version_str}): "
                                f"Methodologies {a.pk} and {b.pk} share type '{key[1]}' "
                                f"(claim_type={key[2]}) with overlapping date ranges."
                            ),
                            affected_objects=[
                                {
                                    "type": "ContractMethodology",
                                    "id": a.pk,
                                    "effective_date": str(a.effective_date),
                                    "termination_date": str(a.termination_date),
                                },
                                {
                                    "type": "ContractMethodology",
                                    "id": b.pk,
                                    "effective_date": str(b.effective_date),
                                    "termination_date": str(b.termination_date),
                                },
                            ],
                            suggested_action=(
                                "Set termination_date on the earlier methodology to "
                                "avoid overlap."
                            ),
                        ))
        return errors

    @classmethod
    def _check_carveout_overlaps(cls, versions) -> List[ConflictError]:
        """
        Detect multiple ContractCarveout rules targeting the same (code_type, code_value)
        within the same contract version.
        """
        from core.models import ContractCarveout
        errors: List[ConflictError] = []
        for version in versions:
            carveouts = list(ContractCarveout.objects.filter(version=version))
            groups: Dict[tuple, list] = defaultdict(list)
            for c in carveouts:
                groups[(c.code_type, c.code_value)].append(c)
            for key, group in groups.items():
                if len(group) > 1:
                    errors.append(ConflictError(
                        conflict_type="CARVEOUT_OVERLAP",
                        severity="ERROR",
                        message=(
                            f"Version {version.pk}: {len(group)} carve-out rules share "
                            f"code_type='{key[0]}', code_value='{key[1]}'. "
                            "Only one carve-out rule can apply per code."
                        ),
                        affected_objects=[
                            {
                                "type": "ContractCarveout",
                                "id": c.pk,
                                "methodology": c.carveout_methodology,
                            }
                            for c in group
                        ],
                        suggested_action="Remove duplicate carve-out rules.",
                    ))
        return errors

    @classmethod
    def _check_blending_cycles(cls, versions) -> List[ConflictError]:
        """
        Build a blending DAG per version and detect directed cycles.
        """
        from core.models import ContractBlendingRule
        errors: List[ConflictError] = []
        for version in versions:
            rules = list(ContractBlendingRule.objects.filter(version=version))
            if len(rules) < 2:
                continue
            cycle = cls._detect_blending_cycle(rules)
            if cycle is None:
                continue
            cycle_set = set(cycle)
            involved = [
                r for r in rules
                if (r.primary_methodology or "").strip() in cycle_set
                or (r.secondary_methodology or "").strip() in cycle_set
            ]
            errors.append(ConflictError(
                conflict_type="BLENDING_CYCLE",
                severity="ERROR",
                message=(
                    f"Version {version.pk}: Blending rules form a cycle: "
                    f"{' → '.join(cycle)}"
                ),
                affected_objects=[
                    {
                        "type": "ContractBlendingRule",
                        "id": r.blending_rule_id,
                        "primary": r.primary_methodology,
                        "secondary": r.secondary_methodology,
                    }
                    for r in involved
                ],
                suggested_action="Remove or break the cycle in blending rule references.",
            ))
        return errors

    @classmethod
    def _check_unreachable_rule_conditions(cls, contract) -> List[ConflictError]:
        """
        ERROR when a PricingRuleCondition references an attribute the engine cannot evaluate.
        """
        from core.models import PricingRule

        evaluable = _evaluable_rule_condition_attributes()
        rules = (
            PricingRule.objects.filter(contract=contract)
            .prefetch_related('conditions')
        )
        errors: List[ConflictError] = []
        seen: set = set()
        for rule in rules:
            for cond in rule.conditions.all():
                raw_attr = (cond.attribute_name or '').strip()
                normalized = _normalize_condition_attribute(raw_attr)
                if raw_attr in evaluable or normalized in evaluable:
                    continue
                key = (rule.pk, cond.pk, raw_attr)
                if key in seen:
                    continue
                seen.add(key)
                errors.append(ConflictError(
                    conflict_type='UNREACHABLE_RULE',
                    severity='ERROR',
                    message=(
                        f"Rule {rule.pk} condition {cond.pk}: attribute_name "
                        f"'{raw_attr}' cannot be evaluated by the pricing engine."
                    ),
                    affected_objects=[
                        {
                            'type': 'PricingRuleCondition',
                            'id': cond.pk,
                            'rule_id': rule.pk,
                            'attribute_name': raw_attr,
                        },
                    ],
                    suggested_action=(
                        'Remove the condition or use an evaluable attribute '
                        f'({", ".join(sorted(evaluable))}).'
                    ),
                ))
        return errors

    @classmethod
    def _check_ambiguous_pricing_rules(cls, contract, versions) -> List[ConflictError]:
        """
        ERROR when two rules in the same version target the same procedure code with
        identical specificity_score but different flat_rate (insertion-order tie).
        """
        from core.models import PricingRule

        version_ids = [v.pk for v in versions]
        rules = list(
            PricingRule.objects.filter(contract=contract, version_id__in=version_ids)
            .prefetch_related('conditions')
        )
        groups: Dict[tuple, list] = defaultdict(list)
        for rule in rules:
            code = _procedure_code_from_rule(rule)
            if not code or rule.version_id is None:
                continue
            key = (rule.version_id, code, rule.specificity_score)
            groups[key].append(rule)

        errors: List[ConflictError] = []
        for (version_id, code, score), group in groups.items():
            if len(group) < 2:
                continue
            flat_rates = {
                r.flat_rate for r in group
                if r.flat_rate is not None
            }
            has_null = any(r.flat_rate is None for r in group)
            distinct_count = len(flat_rates) + (1 if has_null else 0)
            if distinct_count < 2:
                continue
            errors.append(ConflictError(
                conflict_type='AMBIGUOUS_RULE',
                severity='ERROR',
                message=(
                    f"Version {version_id}: {len(group)} rules match procedure code "
                    f"'{code}' with specificity_score {score} but different flat_rate "
                    f"values — resolution depends on insertion order."
                ),
                affected_objects=[
                    {
                        'type': 'PricingRule',
                        'id': r.pk,
                        'flat_rate': str(r.flat_rate) if r.flat_rate is not None else None,
                        'specificity_score': r.specificity_score,
                    }
                    for r in group
                ],
                suggested_action=(
                    'Give rules distinct specificity scores (carve-out) or merge '
                    'duplicate flat rates for the same code.'
                ),
            ))
        return errors

    @classmethod
    def _check_non_canonical_rule_claim_types(cls, contract) -> List[ConflictError]:
        """
        ERROR when PricingRule.claim_type is not NULL or lowercase professional/institutional.
        """
        from core.models import PricingRule

        errors: List[ConflictError] = []
        for rule in PricingRule.objects.filter(contract=contract):
            ct = rule.claim_type
            if ct is None or str(ct).strip() == '':
                continue
            ct_str = str(ct).strip()
            if ct_str != ct_str.lower() or ct_str.lower() not in _CANONICAL_RULE_CLAIM_TYPES:
                errors.append(ConflictError(
                    conflict_type='NON_CANONICAL_CLAIM_TYPE',
                    severity='ERROR',
                    message=(
                        f"Rule {rule.pk}: claim_type '{ct}' is not NULL or lowercase "
                        "professional/institutional — the rule will not match API claims."
                    ),
                    affected_objects=[
                        {
                            'type': 'PricingRule',
                            'id': rule.pk,
                            'claim_type': ct_str,
                        },
                    ],
                    suggested_action=(
                        "Set claim_type to NULL (wildcard) or lowercase 'professional' "
                        "or 'institutional'."
                    ),
                ))
        return errors

    @classmethod
    def _check_pointless_carveouts(cls, contract, versions) -> List[ConflictError]:
        """
        WARNING when a higher-specificity rule pays the same flat_rate as a lower-specificity
        rule for the same procedure code — indistinguishable at runtime.
        """
        from core.models import PricingRule

        version_ids = [v.pk for v in versions]
        rules = list(
            PricingRule.objects.filter(contract=contract, version_id__in=version_ids)
            .prefetch_related('conditions')
        )
        by_version_code: Dict[tuple, list] = defaultdict(list)
        for rule in rules:
            code = _procedure_code_from_rule(rule)
            if not code or rule.version_id is None or rule.flat_rate is None:
                continue
            by_version_code[(rule.version_id, code)].append(rule)

        warnings: List[ConflictError] = []
        seen_pairs: set = set()
        for (_version_id, code), group in by_version_code.items():
            if len(group) < 2:
                continue
            sorted_group = sorted(group, key=lambda r: r.specificity_score)
            for i, lower in enumerate(sorted_group):
                for higher in sorted_group[i + 1:]:
                    if higher.flat_rate != lower.flat_rate:
                        continue
                    pair_key = (lower.pk, higher.pk)
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    warnings.append(ConflictError(
                        conflict_type='POINTLESS_CARVEOUT',
                        severity='WARNING',
                        message=(
                            f"Rule {higher.pk} (score {higher.specificity_score}) "
                            f"carves out procedure code '{code}' but flat_rate "
                            f"{higher.flat_rate} equals lower rule {lower.pk} "
                            f"(score {lower.specificity_score}) — no pricing difference."
                        ),
                        affected_objects=[
                            {
                                'type': 'PricingRule',
                                'id': lower.pk,
                                'specificity_score': lower.specificity_score,
                                'flat_rate': str(lower.flat_rate),
                            },
                            {
                                'type': 'PricingRule',
                                'id': higher.pk,
                                'specificity_score': higher.specificity_score,
                                'flat_rate': str(higher.flat_rate),
                            },
                        ],
                        suggested_action=(
                            'Raise the carve-out flat_rate or remove the redundant rule.'
                        ),
                    ))
        return warnings

    # ------------------------------------------------------------------
    # Cycle detection algorithm
    # ------------------------------------------------------------------

    @classmethod
    def _detect_blending_cycle(cls, rules) -> Optional[List[str]]:
        """
        Build directed graph: edge primary → secondary for each valid blending rule.
        Detect cycles using iterative DFS with colour marking.
        Returns cycle path as list of methodology-code strings, or None if acyclic.
        """
        graph: Dict[str, List[str]] = defaultdict(list)
        nodes = set()
        for rule in rules:
            p = (getattr(rule, "primary_methodology", "") or "").strip()
            s = (getattr(rule, "secondary_methodology", "") or "").strip()
            if not p or not s or p == s:
                continue
            graph[p].append(s)
            nodes.add(p)
            nodes.add(s)

        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {n: WHITE for n in nodes}
        parent: Dict[str, Optional[str]] = {n: None for n in nodes}

        def dfs(start: str) -> Optional[List[str]]:
            stack = [(start, iter(graph.get(start, [])))]
            color[start] = GRAY
            while stack:
                node, neighbours = stack[-1]
                try:
                    nxt = next(neighbours)
                    if color.get(nxt, WHITE) == GRAY:
                        # Cycle found — reconstruct path
                        cycle = [nxt]
                        cur = node
                        while cur != nxt:
                            cycle.append(cur)
                            cur = parent.get(cur) or ""
                            if not cur:
                                break
                        cycle.append(nxt)
                        cycle.reverse()
                        return cycle
                    if color.get(nxt, WHITE) == WHITE:
                        color[nxt] = GRAY
                        parent[nxt] = node
                        stack.append((nxt, iter(graph.get(nxt, []))))
                except StopIteration:
                    color[node] = BLACK
                    stack.pop()
            return None

        for node in nodes:
            if color[node] == WHITE:
                result = dfs(node)
                if result:
                    return result
        return None
