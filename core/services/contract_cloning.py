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
    ContractCapFloor,
    ContractCarveout,
    ContractCoveredEntity,
    ContractEscalator,
    ContractProductScope,
    ContractRateBasis,
    ContractScope,
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
