"""
Gap D (§16): Deep-clone a contract as a template for a new provider/payer.

Never mutates the source contract. Each invocation creates a new ProviderContract (new PKs).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from core.models import (
    ContractArrangement,
    ContractBlendingRule,
    ContractCapFloor,
    ContractCarveout,
    ContractEscalator,
    ContractMethodology,
    ContractOutlierRule,
    ContractRateBasis,
    ContractStopLossRule,
    ContractVersion,
    PricingRule,
    PricingRuleCondition,
    ProviderContract,
    ProviderOrganization,
)
from products.models import PayerOrganization


@dataclass
class CloneSummary:
    source_contract_id: int
    new_contract_id: int
    new_contract_name: str
    source_version_id: int
    new_version_id: int
    counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            'source_contract_id': self.source_contract_id,
            'new_contract_id': self.new_contract_id,
            'new_contract_name': self.new_contract_name,
            'source_version_id': self.source_version_id,
            'new_version_id': self.new_version_id,
            'counts': dict(self.counts),
        }


def _bump(counts: dict[str, int], key: str, n: int = 1) -> None:
    counts[key] = counts.get(key, 0) + n


def _resolve_active_version(contract: ProviderContract) -> ContractVersion:
    version = (
        ContractVersion.objects.filter(
            contract=contract,
            status=ContractVersion.VersionStatus.ACTIVE,
        )
        .order_by('-version_number')
        .first()
    )
    if version is None:
        version = (
            ContractVersion.objects.filter(contract=contract)
            .order_by('-version_number')
            .first()
        )
    if version is None:
        raise ObjectDoesNotExist(f'Contract {contract.contract_id} has no version to clone')
    return version


def _clone_contract_header(
    source: ProviderContract,
    *,
    new_name: str,
    target_provider_org_id: Optional[str] = None,
    target_payer_org_id: Optional[int] = None,
) -> ProviderContract:
    provider_org = source.provider_org
    if target_provider_org_id:
        provider_org = ProviderOrganization.objects.get(organization_id=target_provider_org_id)

    payer_org = source.payer_org
    if target_payer_org_id is not None:
        payer_org = PayerOrganization.objects.get(pk=target_payer_org_id)

    return ProviderContract.objects.create(
        contract_name=new_name,
        legacy_contract_number=None,
        line_of_business=source.line_of_business,
        provider_org=provider_org,
        network=source.network,
        payer_org=payer_org,
        status='DRAFT',
        effective_start_date=source.effective_start_date,
        effective_end_date=source.effective_end_date,
        contract_origin_type=source.contract_origin_type,
        resolution_priority=source.resolution_priority,
    )


def clone_contract(
    source_contract_id: int,
    *,
    new_name: str,
    target_provider_org_id: Optional[str] = None,
    target_payer_org_id: Optional[int] = None,
) -> tuple[ProviderContract, CloneSummary]:
    """
    Deep-clone source contract (ACTIVE version graph) into a new DRAFT contract.
    Returns (new_contract, summary).
    """
    try:
        source = ProviderContract.objects.select_related('provider_org', 'payer_org').get(
            pk=source_contract_id,
        )
    except ProviderContract.DoesNotExist as exc:
        raise ObjectDoesNotExist(f'Source contract {source_contract_id} not found') from exc

    source_version = _resolve_active_version(source)
    counts: dict[str, int] = {}

    with transaction.atomic():
        new_contract = _clone_contract_header(
            source,
            new_name=new_name,
            target_provider_org_id=target_provider_org_id,
            target_payer_org_id=target_payer_org_id,
        )
        _bump(counts, 'ProviderContract')

        new_version = ContractVersion.objects.create(
            contract=new_contract,
            version_number=1,
            effective_start_date=source_version.effective_start_date,
            effective_end_date=source_version.effective_end_date,
            status=ContractVersion.VersionStatus.DRAFT,
            notes=source_version.notes,
            pricing_engine_mode=source_version.pricing_engine_mode,
            claim_level_drg_enabled=source_version.claim_level_drg_enabled,
            product_id=source_version.product_id,
            tier_priority=source_version.tier_priority,
        )
        _bump(counts, 'ContractVersion')

        arrangement_map: dict[int, ContractArrangement] = {}
        for arr in ContractArrangement.objects.filter(contract=source).order_by('id'):
            new_arr = ContractArrangement.objects.create(
                contract=new_contract,
                name=arr.name,
                arrangement_type=arr.arrangement_type,
                claim_type=arr.claim_type,
                effective_start_date=arr.effective_start_date,
                effective_end_date=arr.effective_end_date,
                status=ContractVersion.VersionStatus.DRAFT,
            )
            arrangement_map[arr.id] = new_arr
            _bump(counts, 'ContractArrangement')

        source_rules = PricingRule.objects.filter(
            contract=source,
            version=source_version,
        ).select_related('rate_basis__schedule').prefetch_related('conditions').order_by('rule_id')

        for rule in source_rules:
            new_arr = arrangement_map.get(rule.arrangement_id) if rule.arrangement_id else None
            new_rule = PricingRule.objects.create(
                contract=new_contract,
                version=new_version,
                rule_name=rule.rule_name,
                arrangement=new_arr,
                rule_type=rule.rule_type,
                methodology_code=rule.methodology_code,
                multiplier=rule.multiplier,
                flat_rate=rule.flat_rate,
                contract_term=None,
                per_diem_rate=None,
                flat_rate_override=None,
                base_fee_schedule=rule.base_fee_schedule,
                claim_type=rule.claim_type,
                site_of_service=rule.site_of_service,
                specificity_score=rule.specificity_score,
                status=PricingRule.RuleStatus.DRAFT,
                effective_start_date=rule.effective_start_date,
                effective_end_date=rule.effective_end_date,
            )
            _bump(counts, 'PricingRule')

            for cond in rule.conditions.all():
                PricingRuleCondition.objects.create(
                    pricing_rule=new_rule,
                    attribute_name=cond.attribute_name,
                    operator=cond.operator,
                    attribute_value=cond.attribute_value,
                )
                _bump(counts, 'PricingRuleCondition')

            basis = ContractRateBasis.objects.filter(pricing_rule=rule).first()
            if basis is not None:
                ContractRateBasis.objects.create(
                    pricing_rule=new_rule,
                    schedule=basis.schedule,
                    percentage=basis.percentage,
                )
                _bump(counts, 'ContractRateBasis')

        target_org = new_contract.provider_org
        source_org_id = source.provider_org_id

        for scope in ContractScope.objects.filter(contract=source).order_by('id'):
            ContractScope.objects.create(
                contract=new_contract,
                line_of_business=scope.line_of_business,
                specialty_code=scope.specialty_code,
                site_of_service=scope.site_of_service,
                geo=scope.geo,
                priority=scope.priority,
            )
            _bump(counts, 'ContractScope')

        for ps in ContractProductScope.objects.filter(contract=source).order_by('id'):
            ContractProductScope.objects.create(
                contract=new_contract,
                lob_code=ps.lob_code,
                product=ps.product,
                effective_date=ps.effective_date,
                termination_date=ps.termination_date,
            )
            _bump(counts, 'ContractProductScope')

        for entity in ContractCoveredEntity.objects.filter(contract=source).order_by('id'):
            org = entity.organization
            if (
                target_provider_org_id
                and entity.entity_type == ContractCoveredEntity.EntityType.ORG
                and entity.organization_id == source_org_id
            ):
                org = target_org
            ContractCoveredEntity.objects.create(
                contract=new_contract,
                entity_type=entity.entity_type,
                organization=org if entity.entity_type == ContractCoveredEntity.EntityType.ORG else None,
                facility=entity.facility if entity.entity_type == ContractCoveredEntity.EntityType.FACILITY else None,
                provider=entity.provider if entity.entity_type == ContractCoveredEntity.EntityType.PROVIDER else None,
                is_primary=entity.is_primary,
                effective_start_date=entity.effective_start_date,
                effective_end_date=entity.effective_end_date,
            )
            _bump(counts, 'ContractCoveredEntity')

        for esc in ContractEscalator.objects.filter(contract=source).order_by('id'):
            new_esc_version = None
            if esc.version_id is not None:
                if esc.version_id != source_version.version_id:
                    continue
                new_esc_version = new_version
            ContractEscalator.objects.create(
                contract=new_contract,
                version=new_esc_version,
                annual_percentage=esc.annual_percentage,
                cap_percentage=esc.cap_percentage,
                base_year=esc.base_year,
                effective_start_date=esc.effective_start_date,
                effective_end_date=esc.effective_end_date,
            )
            _bump(counts, 'ContractEscalator')

        for carve in ContractCarveout.objects.filter(version=source_version).order_by('carveout_id'):
            ContractCarveout.objects.create(
                version=new_version,
                code_type=carve.code_type,
                code_value=carve.code_value,
                carveout_methodology=carve.carveout_methodology,
                carveout_percentage=carve.carveout_percentage,
                carveout_rate=carve.carveout_rate,
                status=ContractVersion.VersionStatus.DRAFT,
                conditions=carve.conditions,
            )
            _bump(counts, 'ContractCarveout')

        for cap in ContractCapFloor.objects.filter(version=source_version).order_by('cap_floor_id'):
            ContractCapFloor.objects.create(
                version=new_version,
                scope=cap.scope,
                cap_type=cap.cap_type,
                value=cap.value,
                percentage=cap.percentage,
                code_value=cap.code_value,
                priority=cap.priority,
                effective_start_date=cap.effective_start_date,
                effective_end_date=cap.effective_end_date,
                status=ContractVersion.VersionStatus.DRAFT,
                conditions=cap.conditions,
            )
            _bump(counts, 'ContractCapFloor')

    summary = CloneSummary(
        source_contract_id=source.contract_id,
        new_contract_id=new_contract.contract_id,
        new_contract_name=new_contract.contract_name or new_name,
        source_version_id=source_version.version_id,
        new_version_id=new_version.version_id,
        counts=counts,
    )
    return new_contract, summary


def _clone_version_pricing_graph(
    *,
    source_version: ContractVersion,
    target_version: ContractVersion,
    target_contract: ProviderContract,
    counts: dict[str, int],
) -> None:
    """Copy version-scoped pricing objects onto target_version (same or different contract)."""
    source_rules = PricingRule.objects.filter(
        contract=source_version.contract,
        version=source_version,
    ).select_related('rate_basis__schedule').prefetch_related('conditions').order_by('rule_id')

    for rule in source_rules:
        new_rule = PricingRule.objects.create(
            contract=target_contract,
            version=target_version,
            rule_name=rule.rule_name,
            arrangement=rule.arrangement if rule.arrangement_id and rule.arrangement.contract_id == target_contract.contract_id else None,
            rule_type=rule.rule_type,
            methodology_code=rule.methodology_code,
            multiplier=rule.multiplier,
            flat_rate=rule.flat_rate,
            contract_term=rule.contract_term,
            per_diem_rate=rule.per_diem_rate,
            flat_rate_override=rule.flat_rate_override,
            base_fee_schedule=rule.base_fee_schedule,
            claim_type=rule.claim_type,
            site_of_service=rule.site_of_service,
            specificity_score=rule.specificity_score,
            status=PricingRule.RuleStatus.DRAFT,
            effective_start_date=rule.effective_start_date,
            effective_end_date=rule.effective_end_date,
        )
        _bump(counts, 'PricingRule')

        for cond in rule.conditions.all():
            PricingRuleCondition.objects.create(
                pricing_rule=new_rule,
                attribute_name=cond.attribute_name,
                operator=cond.operator,
                attribute_value=cond.attribute_value,
            )
            _bump(counts, 'PricingRuleCondition')

        basis = ContractRateBasis.objects.filter(pricing_rule=rule).first()
        if basis is not None:
            ContractRateBasis.objects.create(
                pricing_rule=new_rule,
                schedule=basis.schedule,
                percentage=basis.percentage,
            )
            _bump(counts, 'ContractRateBasis')

    for meth in ContractMethodology.objects.filter(
        contract=source_version.contract,
        version=source_version,
    ).order_by('id'):
        ContractMethodology.objects.create(
            contract=target_contract,
            version=target_version,
            methodology_type=meth.methodology_type,
            base_percentage=meth.base_percentage,
            conversion_factor=meth.conversion_factor,
            contract_term=meth.contract_term,
            fee_schedule=meth.fee_schedule,
            effective_date=meth.effective_date,
            termination_date=meth.termination_date,
            priority=meth.priority,
            claim_type=meth.claim_type,
            site_of_service=meth.site_of_service,
            conditions=meth.conditions,
        )
        _bump(counts, 'ContractMethodology')

    for esc in ContractEscalator.objects.filter(
        contract=source_version.contract,
        version=source_version,
    ).order_by('id'):
        ContractEscalator.objects.create(
            contract=target_contract,
            version=target_version,
            annual_percentage=esc.annual_percentage,
            cap_percentage=esc.cap_percentage,
            base_year=esc.base_year,
            effective_start_date=esc.effective_start_date,
            effective_end_date=esc.effective_end_date,
        )
        _bump(counts, 'ContractEscalator')

    for carve in ContractCarveout.objects.filter(version=source_version).order_by('carveout_id'):
        ContractCarveout.objects.create(
            version=target_version,
            code_type=carve.code_type,
            code_value=carve.code_value,
            carveout_methodology=carve.carveout_methodology,
            carveout_percentage=carve.carveout_percentage,
            carveout_rate=carve.carveout_rate,
            status=ContractVersion.VersionStatus.DRAFT,
            conditions=carve.conditions,
        )
        _bump(counts, 'ContractCarveout')

    for cap in ContractCapFloor.objects.filter(version=source_version).order_by('cap_floor_id'):
        ContractCapFloor.objects.create(
            version=target_version,
            scope=cap.scope,
            cap_type=cap.cap_type,
            value=cap.value,
            percentage=cap.percentage,
            code_value=cap.code_value,
            priority=cap.priority,
            effective_start_date=cap.effective_start_date,
            effective_end_date=cap.effective_end_date,
            status=ContractVersion.VersionStatus.DRAFT,
            conditions=cap.conditions,
        )
        _bump(counts, 'ContractCapFloor')

    for blend in ContractBlendingRule.objects.filter(version=source_version).order_by('blending_rule_id'):
        ContractBlendingRule.objects.create(
            version=target_version,
            blend_type=blend.blend_type,
            scope=blend.scope,
            primary_methodology=blend.primary_methodology,
            secondary_methodology=blend.secondary_methodology,
            blend_percentage=blend.blend_percentage,
            priority=blend.priority,
            effective_start_date=blend.effective_start_date,
            effective_end_date=blend.effective_end_date,
            status=ContractVersion.VersionStatus.DRAFT,
            conditions=blend.conditions,
        )
        _bump(counts, 'ContractBlendingRule')

    for outlier in ContractOutlierRule.objects.filter(
        contract=source_version.contract,
        version=source_version,
    ).order_by('id'):
        ContractOutlierRule.objects.create(
            contract=target_contract,
            version=target_version,
            threshold_amount=outlier.threshold_amount,
            threshold_scope=outlier.threshold_scope,
            reimbursement_percentage=outlier.reimbursement_percentage,
            cost_to_charge_ratio=outlier.cost_to_charge_ratio,
            priority=outlier.priority,
            effective_start_date=outlier.effective_start_date,
            effective_end_date=outlier.effective_end_date,
        )
        _bump(counts, 'ContractOutlierRule')

    for stop in ContractStopLossRule.objects.filter(
        contract=source_version.contract,
        version=source_version,
    ).order_by('id'):
        ContractStopLossRule.objects.create(
            contract=target_contract,
            version=target_version,
            cost_threshold=stop.cost_threshold,
            reimbursement_percentage=stop.reimbursement_percentage,
            priority=stop.priority,
            effective_start_date=stop.effective_start_date,
            effective_end_date=stop.effective_end_date,
        )
        _bump(counts, 'ContractStopLossRule')


@dataclass
class VersionCloneSummary:
    source_version_id: int
    new_version_id: int
    version_number: int
    counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            'source_version_id': self.source_version_id,
            'new_version_id': self.new_version_id,
            'version_number': self.version_number,
            'counts': dict(self.counts),
        }


def clone_version_within_contract(
    source_version: ContractVersion,
    *,
    effective_start_date=None,
    notes: str = '',
) -> tuple[ContractVersion, VersionCloneSummary]:
    """
    Clone an ACTIVE (or any) version into a new DRAFT version on the same contract.
    Copies rules, conditions, rate bases, caps/floors/outliers/stop-loss/blending/carveouts.
    Roster (ContractCoveredEntity) and scope (ContractScopeUnified) are contract-level and
    remain shared — no copy required for same-contract amendments.
    """
    contract = source_version.contract
    max_num = (
        ContractVersion.objects.filter(contract=contract)
        .order_by('-version_number')
        .values_list('version_number', flat=True)
        .first()
    ) or 0
    eff_start = effective_start_date or source_version.effective_start_date
    counts: dict[str, int] = {}

    with transaction.atomic():
        new_version = ContractVersion.objects.create(
            contract=contract,
            version_number=max_num + 1,
            effective_start_date=eff_start,
            effective_end_date=source_version.effective_end_date,
            status=ContractVersion.VersionStatus.DRAFT,
            notes=notes or source_version.notes,
            pricing_engine_mode=source_version.pricing_engine_mode,
            claim_level_drg_enabled=source_version.claim_level_drg_enabled,
            product_id=source_version.product_id,
            tier_priority=source_version.tier_priority,
        )
        _bump(counts, 'ContractVersion')

        _clone_version_pricing_graph(
            source_version=source_version,
            target_version=new_version,
            target_contract=contract,
            counts=counts,
        )

    summary = VersionCloneSummary(
        source_version_id=source_version.version_id,
        new_version_id=new_version.version_id,
        version_number=new_version.version_number,
        counts=counts,
    )
    return new_version, summary
