"""
Phase 5C: Materialized contract snapshot cache.

Builds a precomputed contract runtime configuration (methodology + rules + fee schedule refs)
so bulk simulation can avoid re-resolving the methodology graph on every request.
Cache is invalidated when contract methodologies or pricing rules change.
Snapshot is an execution accelerator: get_or_build_pricing_config() returns ContractPricingConfig for the engine.
"""
from datetime import date
from typing import Optional

from django.core.cache import cache
from django.db.models import Q

from core.models import (
    ProviderContract,
    ContractMethodology,
    PricingRule,
    ContractOutlierRule,
    ContractStopLossRule,
    ContractVersion,
    ContractCarveout,
    ContractCapFloor,
    ContractBlendingRule,
)
from core.engine.config import ContractPricingConfig


CACHE_KEY_PREFIX = "contract_snapshot"
CACHE_TIMEOUT = 3600  # 1 hour; None = no expiry


def _cache_key(contract_id: int) -> str:
    return f"{CACHE_KEY_PREFIX}:{contract_id}"


def build_contract_snapshot(contract: ProviderContract) -> dict:
    """
    Build a JSON-serializable snapshot of contract runtime config:
    methodologies, rule ids (with methodology/type), fee schedule refs.
    """
    methodologies = list(
        ContractMethodology.objects.filter(contract=contract)
        .order_by("-effective_date")
        .values("id", "methodology_type", "conversion_factor", "effective_date", "termination_date", "claim_type")
    )
    rules = list(
        PricingRule.objects.filter(contract=contract).values(
            "rule_id", "rule_name", "rule_type", "methodology_code", "status", "specificity_score", "base_fee_schedule_id"
        )
    )
    fee_schedule_ids = set()
    rule_list = []
    for r in rules:
        if r.get("base_fee_schedule_id"):
            fee_schedule_ids.add(r["base_fee_schedule_id"])
        rule_list.append({
            "rule_id": r["rule_id"],
            "rule_name": r["rule_name"],
            "rule_type": r["rule_type"],
            "methodology_code": r["methodology_code"] or "",
            "status": r["status"],
            "specificity_score": r["specificity_score"],
        })
    outlier_rules = list(
        ContractOutlierRule.objects.filter(contract=contract)
        .order_by("-priority", "effective_start_date")
        .values("id", "threshold_amount", "threshold_scope", "reimbursement_percentage", "cost_to_charge_ratio", "priority", "effective_start_date", "effective_end_date")
    )
    stop_loss_rules = list(
        ContractStopLossRule.objects.filter(contract=contract)
        .order_by("-priority", "effective_start_date")
        .values("id", "cost_threshold", "reimbursement_percentage", "priority", "effective_start_date", "effective_end_date")
    )
    # Step 7: include carve-out IDs so snapshot-backed config can reload them
    carveouts = list(
        ContractCarveout.objects.filter(
            version__contract=contract,
        ).order_by("code_type", "code_value")
        .values("carveout_id", "version_id", "code_type", "code_value", "carveout_methodology")
    )
    # Step 8: include cap/floor IDs so snapshot-backed config can reload them
    cap_floors = list(
        ContractCapFloor.objects.filter(
            version__contract=contract,
        ).order_by("-priority", "effective_start_date")
        .values("cap_floor_id", "version_id", "scope", "cap_type", "priority",
                "effective_start_date", "effective_end_date")
    )
    # Step 9: include blending rule IDs so snapshot-backed config can reload them
    blending_rules = list(
        ContractBlendingRule.objects.filter(
            version__contract=contract,
        ).order_by("-priority", "effective_start_date")
        .values("blending_rule_id", "version_id", "blend_type", "scope",
                "blend_percentage", "priority", "effective_start_date", "effective_end_date")
    )
    snapshot = {
        "contract_id": contract.pk,
        "contract_name": getattr(contract, "contract_name", "") or "",
        "methodologies": methodologies,
        "rules": rule_list,
        "fee_schedule_ids": list(fee_schedule_ids),
        "outlier_rules": outlier_rules,
        "stop_loss_rules": stop_loss_rules,
        "carveouts": carveouts,
        "cap_floors": cap_floors,
        "blending_rules": blending_rules,
    }
    return snapshot


def get_cached_snapshot(contract_id: int) -> dict | None:
    """Return cached snapshot for contract if present."""
    return cache.get(_cache_key(contract_id))


def get_or_build_snapshot(contract: ProviderContract) -> dict:
    """Return cached snapshot or build, cache, and return."""
    key = _cache_key(contract.pk)
    snapshot = cache.get(key)
    if snapshot is not None:
        return snapshot
    snapshot = build_contract_snapshot(contract)
    cache.set(key, snapshot, CACHE_TIMEOUT)
    return snapshot


def invalidate_snapshot(contract_id: int) -> None:
    """Invalidate cached snapshot when contract config changes."""
    cache.delete(_cache_key(contract_id))


def build_contract_pricing_config_from_snapshot(
    contract: ProviderContract,
    service_date: date,
    version: Optional[ContractVersion],
    snapshot_dict: dict,
) -> ContractPricingConfig:
    """
    Build an immutable ContractPricingConfig from a snapshot dict (e.g. from get_or_build_snapshot).
    Loads full ORM objects for rules (with conditions), methodologies, stop_loss, outlier by ids in snapshot.
    ContractPricingConfig is request-scoped and must not be mutated.
    """
    rule_ids = [r["rule_id"] for r in snapshot_dict.get("rules", [])]
    rules_qs = (
        PricingRule.objects.filter(rule_id__in=rule_ids, contract=contract)
        .filter(status=PricingRule.RuleStatus.ACTIVE)
        .filter(effective_start_date__lte=service_date)
        .filter(Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date))
        .select_related("contract", "base_fee_schedule")
        .prefetch_related("conditions")
    )
    if version is not None:
        rules_qs = rules_qs.filter(Q(version=version) | Q(version__isnull=True))
    else:
        rules_qs = rules_qs.filter(version__isnull=True)
    rules = tuple(rules_qs.order_by("-specificity_score"))

    methodology_ids = [m["id"] for m in snapshot_dict.get("methodologies", [])]
    methodologies_qs = ContractMethodology.objects.filter(
        id__in=methodology_ids,
        contract=contract,
        effective_date__lte=service_date,
    ).filter(Q(termination_date__isnull=True) | Q(termination_date__gte=service_date))
    if version is not None:
        methodologies_qs = methodologies_qs.filter(Q(version=version) | Q(version__isnull=True))
    else:
        methodologies_qs = methodologies_qs.filter(version__isnull=True)
    methodologies = tuple(methodologies_qs.order_by("-priority", "-effective_date"))

    stop_ids = [s["id"] for s in snapshot_dict.get("stop_loss_rules", [])]
    stoploss_qs = (
        ContractStopLossRule.objects.filter(id__in=stop_ids, contract=contract)
        .filter(effective_start_date__lte=service_date)
        .filter(Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date))
        .order_by("-priority")
    )
    if version is not None:
        stoploss_qs = stoploss_qs.filter(Q(version=version) | Q(version__isnull=True))
    else:
        stoploss_qs = stoploss_qs.filter(version__isnull=True)
    stop_loss_rules = tuple(stoploss_qs)

    out_ids = [o["id"] for o in snapshot_dict.get("outlier_rules", [])]
    outlier_qs = (
        ContractOutlierRule.objects.filter(id__in=out_ids, contract=contract)
        .filter(effective_start_date__lte=service_date)
        .filter(Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date))
        .order_by("-priority")
    )
    if version is not None:
        outlier_qs = outlier_qs.filter(Q(version=version) | Q(version__isnull=True))
    else:
        outlier_qs = outlier_qs.filter(version__isnull=True)
    outlier_rules = tuple(outlier_qs)

    # Step 7: load carve-outs from snapshot IDs (version-scoped)
    carveout_ids = [c["carveout_id"] for c in snapshot_dict.get("carveouts", [])
                    if version is None or c.get("version_id") == version.pk]
    carveouts = tuple(
        ContractCarveout.objects.filter(carveout_id__in=carveout_ids)
        .order_by("code_type", "code_value")
    ) if carveout_ids else ()

    # Step 8: load cap/floors from snapshot IDs (version-scoped, date-filtered)
    cap_floor_ids = [c["cap_floor_id"] for c in snapshot_dict.get("cap_floors", [])
                     if version is None or c.get("version_id") == version.pk]
    cap_floors_qs = (
        ContractCapFloor.objects.filter(cap_floor_id__in=cap_floor_ids)
        .filter(effective_start_date__lte=service_date)
        .filter(Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date))
        .order_by("-priority", "effective_start_date")
    )
    cap_floors = tuple(cap_floors_qs)

    # Step 9: load blending rules from snapshot IDs (version-scoped, date-filtered)
    blending_rule_ids = [
        b["blending_rule_id"] for b in snapshot_dict.get("blending_rules", [])
        if version is None or b.get("version_id") == version.pk
    ]
    blending_rules_qs = (
        ContractBlendingRule.objects.filter(blending_rule_id__in=blending_rule_ids)
        .filter(effective_start_date__lte=service_date)
        .filter(Q(effective_end_date__isnull=True) | Q(effective_end_date__gte=service_date))
        .order_by("-priority", "effective_start_date")
    )
    blending_rules = tuple(blending_rules_qs)

    return ContractPricingConfig(
        contract=contract,
        version=version,
        service_date=service_date,
        rules=rules,
        methodologies=methodologies,
        stop_loss_rules=stop_loss_rules,
        outlier_rules=outlier_rules,
        carveouts=carveouts,
        cap_floors=cap_floors,
        blending_rules=blending_rules,
    )


def get_or_build_pricing_config(
    contract: ProviderContract,
    service_date: date,
    version: Optional[ContractVersion] = None,
) -> ContractPricingConfig:
    """
    Return ContractPricingConfig for the contract/version/date, using snapshot cache when available.
    Snapshot is an execution accelerator: reduces repeated contract/rule lookups.
    """
    snapshot = get_or_build_snapshot(contract)
    return build_contract_pricing_config_from_snapshot(contract, service_date, version, snapshot)
