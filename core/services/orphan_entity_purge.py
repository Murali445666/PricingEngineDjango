"""
Compute protected entity sets from ACTIVE contracts and purge orphan directory rows.

Never deletes Ref* tables, ProviderContract rows, or pricing rules.
Archive safety: entities referenced by ANY contract in a way that would CASCADE-delete
contracts or covered-entity rows are always kept.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.core.management import call_command
from django.db import transaction
from django.db.models import Q

from core.models import (
    ContractCoveredEntity,
    ContractProductScope,
    ContractScopeUnified,
    ContractVersion,
    PayerNetwork,
    PricingRuleCondition,
    ProviderContract,
    ProviderOrganization,
)
from members.models import Enrollment, Member
from products.models import (
    LineOfBusiness,
    Network,
    PayerOrganization,
    Product,
    ProductNetworkConfig,
)
from providers.models import (
    Facility,
    FacilityNetworkParticipation,
    Provider,
    ProviderAffiliation,
    ProviderNetworkParticipation,
)

ACTIVE_CONTRACT_STATUS = 'ACTIVE'
SAMPLE_DEFAULT = 5

DUMP_LABELS = [
    'providers.provider',
    'providers.facility',
    'providers.provideraffiliation',
    'providers.providernetworkparticipation',
    'providers.facilitynetworkparticipation',
    'members.member',
    'members.enrollment',
    'products.payerorganization',
    'products.lineofbusiness',
    'products.product',
    'products.network',
    'products.productnetworkconfig',
    'core.providerorganization',
    'core.payernetwork',
]


@dataclass
class ProtectedSets:
    org_ids: set[str] = field(default_factory=set)
    provider_ids: set[int] = field(default_factory=set)
    facility_ids: set[int] = field(default_factory=set)
    member_ids: set[int] = field(default_factory=set)
    enrollment_ids: set[int] = field(default_factory=set)
    product_ids: set[int] = field(default_factory=set)
    payer_org_ids: set[int] = field(default_factory=set)
    lob_ids: set[int] = field(default_factory=set)
    network_ids: set[int] = field(default_factory=set)
    payer_network_ids: set[str] = field(default_factory=set)


@dataclass
class PurgePlan:
    protected: ProtectedSets
    delete_counts: dict[str, int] = field(default_factory=dict)
    samples: dict[str, list[str]] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)
    delete_id_sets: dict[str, set] = field(default_factory=dict)


@dataclass
class PurgeResult:
    plan: PurgePlan
    backup_path: str | None = None
    deleted: dict[str, int] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)


def _active_contract_qs():
    return ProviderContract.objects.filter(status=ACTIVE_CONTRACT_STATUS)


def _add_org_parent_chain(org_ids: set[str]) -> None:
    changed = True
    while changed:
        changed = False
        parents = (
            ProviderOrganization.objects.filter(organization_id__in=org_ids)
            .exclude(parent_org__isnull=True)
            .values_list('parent_org_id', flat=True)
        )
        for parent_id in parents:
            if parent_id and parent_id not in org_ids:
                org_ids.add(parent_id)
                changed = True


def _apply_archive_safety(protected: ProtectedSets) -> None:
    """
    Keep entities whose deletion would CASCADE-delete contracts or covered-entity rows.

    Products on archived contract scopes use SET_NULL — they are not protected here.
    """
    protected.org_ids.update(
        ProviderContract.objects.exclude(provider_org_id__isnull=True)
        .values_list('provider_org_id', flat=True)
    )
    protected.org_ids.update(
        ContractCoveredEntity.objects.exclude(organization__isnull=True)
        .values_list('organization_id', flat=True)
    )
    protected.payer_network_ids.update(
        ProviderContract.objects.exclude(network_id__isnull=True)
        .values_list('network_id', flat=True)
    )
    # Deleting an org CASCADE-deletes its PayerNetwork rows; protect orgs that own
    # networks still referenced by any contract (including ARCHIVED).
    protected.org_ids.update(
        PayerNetwork.objects.filter(network_id__in=protected.payer_network_ids)
        .exclude(payer_org_id__isnull=True)
        .values_list('payer_org_id', flat=True)
    )
    protected.provider_ids.update(
        ContractCoveredEntity.objects.exclude(provider__isnull=True)
        .values_list('provider_id', flat=True)
    )
    protected.facility_ids.update(
        ContractCoveredEntity.objects.exclude(facility__isnull=True)
        .values_list('facility_id', flat=True)
    )


def compute_protected_sets() -> ProtectedSets:
    """Build the PROTECTED set from ACTIVE contracts (plus archive safety anchors)."""
    protected = ProtectedSets()
    active_contracts = _active_contract_qs()
    active_contract_ids = list(active_contracts.values_list('pk', flat=True))

    # Contract header FKs on ACTIVE contracts.
    for org_id, network_id, payer_id in active_contracts.values_list(
        'provider_org_id', 'network_id', 'payer_org_id'
    ):
        if org_id:
            protected.org_ids.add(org_id)
        if network_id:
            protected.payer_network_ids.add(network_id)
        if payer_id:
            protected.payer_org_ids.add(payer_id)

    # Covered entities on ACTIVE contracts.
    ce_qs = ContractCoveredEntity.objects.filter(contract_id__in=active_contract_ids)
    protected.org_ids.update(
        ce_qs.exclude(organization__isnull=True).values_list('organization_id', flat=True)
    )
    protected.facility_ids.update(
        ce_qs.exclude(facility__isnull=True).values_list('facility_id', flat=True)
    )
    protected.provider_ids.update(
        ce_qs.exclude(provider__isnull=True).values_list('provider_id', flat=True)
    )

    _add_org_parent_chain(protected.org_ids)

    # Provider carve-outs on ACTIVE contract versions (e.g. Dr. Chen).
    active_version_ids = ContractVersion.objects.filter(
        contract_id__in=active_contract_ids,
    ).values_list('pk', flat=True)
    for raw_provider_id in PricingRuleCondition.objects.filter(
        attribute_name='provider_id',
        pricing_rule__version_id__in=active_version_ids,
    ).values_list('attribute_value', flat=True):
        raw = (raw_provider_id or '').strip()
        if raw.isdigit():
            protected.provider_ids.add(int(raw))

    # Affiliations to protected orgs → protect affiliated providers.
    protected.provider_ids.update(
        ProviderAffiliation.objects.filter(organization_id__in=protected.org_ids)
        .values_list('provider_id', flat=True)
    )

    # Product scope on ACTIVE contracts → products, payers, LOBs, networks.
    scope_product_ids = set(
        ContractScopeUnified.objects.filter(contract_id__in=active_contract_ids)
        .exclude(product__isnull=True)
        .values_list('product_id', flat=True)
    )
    scope_product_ids.update(
        ContractProductScope.objects.filter(contract_id__in=active_contract_ids)
        .exclude(product__isnull=True)
        .values_list('product_id', flat=True)
    )
    protected.product_ids.update(scope_product_ids)

    if protected.product_ids:
        for product_id, payer_id, lob_id in Product.objects.filter(
            pk__in=protected.product_ids
        ).values_list('pk', 'payer_id', 'lob_id'):
            protected.product_ids.add(product_id)
            if payer_id:
                protected.payer_org_ids.add(payer_id)
            if lob_id:
                protected.lob_ids.add(lob_id)

        protected.network_ids.update(
            ProductNetworkConfig.objects.filter(product_id__in=protected.product_ids)
            .values_list('network_id', flat=True)
        )

    # products.Network bridged to protected PayerNetwork rows.
    if protected.payer_network_ids:
        protected.network_ids.update(
            Network.objects.filter(legacy_payer_network_id__in=protected.payer_network_ids)
            .values_list('pk', flat=True)
        )

    # Members enrolled in scoped products (+ their enrollments).
    if protected.product_ids:
        enrollment_rows = Enrollment.objects.filter(
            product_id__in=protected.product_ids
        ).values_list('pk', 'member_id')
        for enrollment_id, member_id in enrollment_rows:
            protected.enrollment_ids.add(enrollment_id)
            protected.member_ids.add(member_id)

    # PayerNetwork / payer org linkage for protected payer networks.
    if protected.payer_network_ids:
        for network_id, payer_org_id in PayerNetwork.objects.filter(
            network_id__in=protected.payer_network_ids
        ).values_list('network_id', 'payer_org_id'):
            protected.payer_network_ids.add(network_id)
            if payer_org_id:
                protected.org_ids.add(payer_org_id)

    if protected.payer_org_ids:
        protected.payer_org_ids.update(
            PayerOrganization.objects.filter(pk__in=protected.payer_org_ids)
            .values_list('pk', flat=True)
        )

    if protected.network_ids:
        protected.network_ids.update(
            Network.objects.filter(pk__in=protected.network_ids).values_list('pk', flat=True)
        )

    if protected.lob_ids:
        protected.lob_ids.update(
            LineOfBusiness.objects.filter(pk__in=protected.lob_ids).values_list('pk', flat=True)
        )

    _add_org_parent_chain(protected.org_ids)
    _apply_archive_safety(protected)

    return protected


def _sample_labels(model, ids: set, label_fn, limit: int) -> list[str]:
    if not ids:
        return []
    rows = model.objects.filter(pk__in=ids).order_by('pk')[:limit]
    return [label_fn(row) for row in rows]


def build_purge_plan(*, sample_size: int = SAMPLE_DEFAULT) -> PurgePlan:
    protected = compute_protected_sets()

    all_provider_ids = set(Provider.objects.values_list('pk', flat=True))
    all_facility_ids = set(Facility.objects.values_list('pk', flat=True))
    all_member_ids = set(Member.objects.values_list('pk', flat=True))
    all_product_ids = set(Product.objects.values_list('pk', flat=True))
    all_payer_org_ids = set(PayerOrganization.objects.values_list('pk', flat=True))
    all_lob_ids = set(LineOfBusiness.objects.values_list('pk', flat=True))
    all_network_ids = set(Network.objects.values_list('pk', flat=True))
    all_org_ids = set(ProviderOrganization.objects.values_list('pk', flat=True))
    all_payer_network_ids = set(PayerNetwork.objects.values_list('pk', flat=True))

    delete_provider_ids = all_provider_ids - protected.provider_ids
    delete_facility_ids = all_facility_ids - protected.facility_ids
    delete_member_ids = all_member_ids - protected.member_ids
    delete_product_ids = all_product_ids - protected.product_ids
    delete_payer_org_ids = all_payer_org_ids - protected.payer_org_ids
    delete_network_ids = all_network_ids - protected.network_ids
    delete_org_ids = all_org_ids - protected.org_ids
    delete_payer_network_ids = all_payer_network_ids - protected.payer_network_ids

    delete_enrollment_ids = set(
        Enrollment.objects.exclude(pk__in=protected.enrollment_ids)
        .filter(
            Q(member_id__in=delete_member_ids)
            | Q(product_id__in=delete_product_ids)
        )
        .values_list('pk', flat=True)
    )
    delete_affiliation_ids = set(
        ProviderAffiliation.objects.filter(
            Q(provider_id__in=delete_provider_ids)
            | Q(organization_id__in=delete_org_ids)
        ).values_list('pk', flat=True)
    )
    delete_provider_participation_ids = set(
        ProviderNetworkParticipation.objects.filter(
            Q(organization_id__in=delete_org_ids)
            | Q(provider_id__in=delete_provider_ids)
        ).values_list('pk', flat=True)
    )
    delete_facility_participation_ids = set(
        FacilityNetworkParticipation.objects.filter(
            facility_id__in=delete_facility_ids
        ).values_list('pk', flat=True)
    )
    delete_pnc_ids = set(
        ProductNetworkConfig.objects.filter(
            Q(product_id__in=delete_product_ids)
            | Q(network_id__in=delete_network_ids)
        ).values_list('pk', flat=True)
    )

    remaining_product_lob_ids = set(
        Product.objects.filter(pk__in=protected.product_ids).values_list('lob_id', flat=True)
    )
    delete_lob_ids = (all_lob_ids - protected.lob_ids) - remaining_product_lob_ids

    totals = {
        'providers': len(all_provider_ids),
        'facilities': len(all_facility_ids),
        'members': len(all_member_ids),
        'enrollments': Enrollment.objects.count(),
        'affiliations': ProviderAffiliation.objects.count(),
        'provider_participations': ProviderNetworkParticipation.objects.count(),
        'facility_participations': FacilityNetworkParticipation.objects.count(),
        'products': len(all_product_ids),
        'product_network_configs': ProductNetworkConfig.objects.count(),
        'networks': len(all_network_ids),
        'payer_organizations': len(all_payer_org_ids),
        'lines_of_business': len(all_lob_ids),
        'provider_organizations': len(all_org_ids),
        'payer_networks': len(all_payer_network_ids),
    }

    delete_counts = {
        'enrollments': len(delete_enrollment_ids),
        'provider_affiliations': len(delete_affiliation_ids),
        'provider_network_participations': len(delete_provider_participation_ids),
        'facility_network_participations': len(delete_facility_participation_ids),
        'product_network_configs': len(delete_pnc_ids),
        'providers': len(delete_provider_ids),
        'facilities': len(delete_facility_ids),
        'members': len(delete_member_ids),
        'products': len(delete_product_ids),
        'networks': len(delete_network_ids),
        'payer_organizations': len(delete_payer_org_ids),
        'lines_of_business': len(delete_lob_ids),
        'payer_networks': len(delete_payer_network_ids),
        'provider_organizations': len(delete_org_ids),
    }

    samples = {
        'providers': _sample_labels(
            Provider, delete_provider_ids, lambda p: p.npi, sample_size
        ),
        'members': _sample_labels(
            Member, delete_member_ids, lambda m: m.member_id, sample_size
        ),
        'facilities': _sample_labels(
            Facility, delete_facility_ids, lambda f: f.npi, sample_size
        ),
        'provider_organizations': _sample_labels(
            ProviderOrganization,
            delete_org_ids,
            lambda o: o.organization_id,
            sample_size,
        ),
    }

    return PurgePlan(
        protected=protected,
        delete_counts=delete_counts,
        samples=samples,
        totals=totals,
        delete_id_sets={
            'enrollments': delete_enrollment_ids,
            'provider_affiliations': delete_affiliation_ids,
            'provider_network_participations': delete_provider_participation_ids,
            'facility_network_participations': delete_facility_participation_ids,
            'product_network_configs': delete_pnc_ids,
            'providers': delete_provider_ids,
            'facilities': delete_facility_ids,
            'members': delete_member_ids,
            'products': delete_product_ids,
            'networks': delete_network_ids,
            'payer_organizations': delete_payer_org_ids,
            'lines_of_business': delete_lob_ids,
            'payer_networks': delete_payer_network_ids,
            'provider_organizations': delete_org_ids,
        },
    )


def _write_backup(backup_dir: Path) -> str:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = backup_dir / f'orphan_entity_purge_{timestamp}.json'
    call_command(
        'dumpdata',
        *DUMP_LABELS,
        '--indent',
        '2',
        '--output',
        str(backup_path),
    )
    return str(backup_path)


def _delete_by_ids(model, ids: set[int] | set[str]) -> int:
    if not ids:
        return 0
    _, details = model.objects.filter(pk__in=ids).delete()
    label = f'{model._meta.app_label}.{model._meta.object_name}'
    return details.get(label, sum(details.values()))


def execute_purge(plan: PurgePlan, *, backup_dir: Path) -> PurgeResult:
    delete_sets = plan.delete_id_sets
    backup_path = _write_backup(backup_dir)
    deleted: dict[str, int] = {}

    with transaction.atomic():
        deleted['enrollments'] = _delete_by_ids(Enrollment, delete_sets['enrollments'])
        deleted['provider_affiliations'] = _delete_by_ids(
            ProviderAffiliation, delete_sets['provider_affiliations']
        )
        deleted['provider_network_participations'] = _delete_by_ids(
            ProviderNetworkParticipation, delete_sets['provider_network_participations']
        )
        deleted['facility_network_participations'] = _delete_by_ids(
            FacilityNetworkParticipation, delete_sets['facility_network_participations']
        )
        deleted['product_network_configs'] = _delete_by_ids(
            ProductNetworkConfig, delete_sets['product_network_configs']
        )
        deleted['providers'] = _delete_by_ids(Provider, delete_sets['providers'])
        deleted['facilities'] = _delete_by_ids(Facility, delete_sets['facilities'])
        deleted['members'] = _delete_by_ids(Member, delete_sets['members'])
        deleted['products'] = _delete_by_ids(Product, delete_sets['products'])
        deleted['networks'] = _delete_by_ids(Network, delete_sets['networks'])
        deleted['payer_organizations'] = _delete_by_ids(
            PayerOrganization, delete_sets['payer_organizations']
        )
        deleted['lines_of_business'] = _delete_by_ids(
            LineOfBusiness, delete_sets['lines_of_business']
        )
        deleted['payer_networks'] = _delete_by_ids(
            PayerNetwork, delete_sets['payer_networks']
        )
        deleted['provider_organizations'] = _delete_by_ids(
            ProviderOrganization, delete_sets['provider_organizations']
        )

    verification = verify_post_purge()
    return PurgeResult(plan=plan, backup_path=backup_path, deleted=deleted, verification=verification)


def verify_post_purge() -> dict[str, Any]:
    """Smoke checks after --apply."""
    from core.engine.service import ClaimPricingService
    from core.engine.types import RawClaimInput
    from core.services.contract_resolution_service import (
        RESOLUTION_PROCEEDS_TO_PRICING,
        ContractResolutionService,
    )
    from core.services.pricing_context_resolver import PricingContextResolver
    from core.services.validation_service import ValidationService

    def _price(billing: str, rendering: str | None) -> tuple[Decimal, int]:
        raw = RawClaimInput(
            billing_npi=billing,
            rendering_npi=rendering,
            member_id='KHS-MEM-0001',
            service_date=date(2025, 6, 15),
            claim_type='professional',
            lines=[{'procedure_code': '99213', 'billed_amount': Decimal('200.00'), 'units': 1}],
        )
        resolution = ContractResolutionService().resolve(raw, member_context=True)
        if resolution.status not in RESOLUTION_PROCEEDS_TO_PRICING:
            raise RuntimeError(f'Pricing resolution failed: {resolution.status} {resolution.reason}')
        ctx = PricingContextResolver().context_from_resolution(raw, resolution)
        line = ClaimPricingService().price_claim_from_context(ctx).lines[0]
        return line.allowed_amount, line.rule_id

    p1_amount, p1_rule = _price('KEYSTONE-NPI02', None)
    p5_amount, p5_rule = _price('KEYSTONE-NPI02', 'KEYSTONE-NPI05')
    conflicts = ValidationService.validate_contract(217)
    error_count = sum(1 for c in conflicts if c.severity == 'ERROR')
    warning_count = sum(1 for c in conflicts if c.severity == 'WARNING')

    return {
        'p1_allowed': str(p1_amount),
        'p1_rule_id': p1_rule,
        'p5_allowed': str(p5_amount),
        'p5_rule_id': p5_rule,
        'validation_errors': error_count,
        'validation_warnings': warning_count,
        'provider_count': Provider.objects.count(),
        'member_count': Member.objects.count(),
        'active_contracts': ProviderContract.objects.filter(status=ACTIVE_CONTRACT_STATUS).count(),
    }
