"""
Highmark–Keystone clean contract seed (CURSOR_SEED_BRIEF).

Idempotent entity graph from docs/provider_roster.csv and docs/members.csv.
Mirrors wiring patterns in core/demo/seed_keystone.py.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction

from core.models import (
    ContractArrangement,
    ContractCoveredEntity,
    ContractProductScope,
    ContractVersion,
    PayerNetwork,
    ProviderContract,
    ProviderOrganization,
    RefSpecialty,
)
from members.models import Enrollment, Member
from products.models import LineOfBusiness, Network, PayerOrganization, Product, ProductNetworkConfig
from providers.models import (
    Facility,
    FacilityNetworkParticipation,
    Provider,
    ProviderAffiliation,
    ProviderNetworkParticipation,
)
from core.services.scope_unified_sync import upsert_unified_product_scope

logger = logging.getLogger(__name__)

EFFECTIVE_START = date(2025, 1, 1)
CONTRACT_LEGACY = 'HM-KHS-2025-0417'
CONTRACT_NAME = 'Highmark – Keystone Health System (Commercial PPO)'

PAYER_ID = 'HIGHMARK'
PAYER_CORE_ORG = 'HIGHMARK-CORE'
PRODUCT_CODE = 'KHS-PPO'
NETWORK_CODE = 'HIGHMARK-PPO'

ORG_SPECS = [
    {
        'key': 'KHS-IDN',
        'org_id': 'KEYSTONE-IDN',
        'name': 'Keystone Health System, Inc.',
        'npi': 'KEYSTONE-NPI01',
        'parent': None,
        'org_type': 'HEALTH_SYSTEM',
    },
    {
        'key': 'KHS-GEN',
        'org_id': 'KHS-GEN',
        'name': 'Keystone General Hospital',
        'npi': 'KEYSTONE-NPI03',
        'parent': 'KHS-IDN',
        'org_type': 'FACILITY',
    },
    {
        'key': 'KHS-CHILD',
        'org_id': 'KHS-CHILD',
        'name': "Keystone Children's Hospital",
        'npi': 'KEYSTONE-NPI04',
        'parent': 'KHS-IDN',
        'org_type': 'FACILITY',
    },
    {
        'key': 'KHS-CARD',
        'org_id': 'KEYSTONE-CARD',
        'name': 'Keystone Cardiology Associates',
        'npi': 'KEYSTONE-NPI02',
        'parent': 'KHS-IDN',
        'org_type': 'GROUP',
    },
    {
        'key': 'KHS-IMG',
        'org_id': 'KHS-IMG',
        'name': 'Keystone Imaging Center',
        'npi': 'KEYSTONE-NPI06',
        'parent': 'KHS-IDN',
        'org_type': 'GROUP',
    },
    {
        'key': 'KHS-BH',
        'org_id': 'KHS-BH',
        'name': 'Keystone Behavioral Health',
        'npi': 'KEYSTONE-NPI07',
        'parent': 'KHS-IDN',
        'org_type': 'GROUP',
    },
]

FACILITY_SPECS = [
    {
        'key': 'KHS-GEN',
        'npi': 'KEYSTONE-NPI03',
        'ccn': 'KHS-GEN',
        'name': 'Keystone General Hospital',
        'facility_type': Facility.FacilityType.HOSPITAL_OUTPATIENT,
    },
    {
        'key': 'KHS-CHILD',
        'npi': 'KEYSTONE-NPI04',
        'ccn': 'KHS-CHILD',
        'name': "Keystone Children's Hospital",
        'facility_type': Facility.FacilityType.HOSPITAL_OUTPATIENT,
    },
    {
        'key': 'KHS-IMG',
        'npi': 'KEYSTONE-NPI06',
        'ccn': 'KHS-IMG',
        'name': 'Keystone Imaging Center',
        'facility_type': Facility.FacilityType.IMAGING,
    },
    {
        'key': 'KHS-BH',
        'npi': 'KEYSTONE-NPI07',
        'ccn': 'KHS-BH',
        'name': 'Keystone Behavioral Health',
        'facility_type': Facility.FacilityType.OFFICE,
    },
]

_stats: dict[str, int] = {}


def _bump(key: str, n: int = 1) -> None:
    _stats[key] = _stats.get(key, 0) + n


def _parse_date(value: str | None) -> date | None:
    if not value or not str(value).strip():
        return None
    return datetime.strptime(str(value).strip(), '%Y-%m-%d').date()


class AgreementContext:
    """Shared cast for the Highmark–Keystone agreement seed."""

    def __init__(self) -> None:
        self.payer_core: ProviderOrganization | None = None
        self.payer: PayerOrganization | None = None
        self.lob: LineOfBusiness | None = None
        self.product: Product | None = None
        self.legacy_network: PayerNetwork | None = None
        self.network: Network | None = None
        self.orgs: dict[str, ProviderOrganization] = {}
        self.facilities: dict[str, Facility] = {}
        self.contract: ProviderContract | None = None
        self.version: ContractVersion | None = None


def _default_docs_dir() -> Path:
    return Path(settings.BASE_DIR) / 'docs'


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def _upsert_payer_stack(ctx: AgreementContext) -> None:
    ctx.payer_core, created = ProviderOrganization.objects.update_or_create(
        organization_id=PAYER_CORE_ORG,
        defaults={
            'name': 'Highmark Health Plan, Inc.',
            'tax_id': '99-HIGHMARK',
        },
    )
    if created:
        _bump('ProviderOrganization')

    ctx.payer, created = PayerOrganization.objects.update_or_create(
        payer_id=PAYER_ID,
        defaults={
            'name': 'Highmark Health Plan, Inc.',
            'payer_type': PayerOrganization.PayerType.COMMERCIAL,
            'legacy_provider_org': ctx.payer_core,
        },
    )
    if created:
        _bump('PayerOrganization')

    ctx.lob, created = LineOfBusiness.objects.get_or_create(
        code='COMMERCIAL',
        defaults={'name': 'Commercial'},
    )
    if created:
        _bump('LineOfBusiness')

    ctx.legacy_network, created = PayerNetwork.objects.update_or_create(
        network_id=NETWORK_CODE,
        defaults={
            'network_name': 'Highmark Commercial PPO',
            'payer_org': ctx.payer_core,
            'line_of_business': 'COMMERCIAL',
            'network_type': 'PPO',
        },
    )
    if created:
        _bump('PayerNetwork')

    ctx.network, created = Network.objects.update_or_create(
        network_code=NETWORK_CODE,
        defaults={
            'payer': ctx.payer,
            'name': 'Highmark Commercial PPO',
            'network_type': Network.NetworkType.PPO,
            'legacy_payer_network': ctx.legacy_network,
        },
    )
    if created:
        _bump('Network')

    ctx.product, created = Product.objects.update_or_create(
        product_code=PRODUCT_CODE,
        defaults={
            'payer': ctx.payer,
            'lob': ctx.lob,
            'name': 'Highmark Commercial PPO',
            'effective_date': EFFECTIVE_START,
            'termination_date': None,
        },
    )
    if created:
        _bump('Product')

    _, pnc_created = ProductNetworkConfig.objects.update_or_create(
        product=ctx.product,
        network=ctx.network,
        claim_type=ProductNetworkConfig.ClaimType.ALL,
        effective_date=EFFECTIVE_START,
        defaults={'termination_date': None},
    )
    if pnc_created:
        _bump('ProductNetworkConfig')


def _upsert_orgs(ctx: AgreementContext) -> None:
    for spec in ORG_SPECS:
        parent = ctx.orgs.get(spec['parent']) if spec['parent'] else None
        org, created = ProviderOrganization.objects.update_or_create(
            organization_id=spec['org_id'],
            defaults={
                'name': spec['name'],
                'npi': spec['npi'],
                'org_type': spec['org_type'],
                'parent_org': parent,
            },
        )
        ctx.orgs[spec['key']] = org
        if created:
            _bump('ProviderOrganization')


def _upsert_facilities(ctx: AgreementContext) -> None:
    for spec in FACILITY_SPECS:
        fac, created = Facility.objects.update_or_create(
            npi=spec['npi'],
            defaults={
                'ccn': spec['ccn'],
                'name': spec['name'],
                'facility_type': spec['facility_type'],
                'status': 'ACTIVE',
            },
        )
        ctx.facilities[spec['key']] = fac
        if created:
            _bump('Facility')


def _upsert_network_participation(ctx: AgreementContext) -> None:
    assert ctx.legacy_network and ctx.network
    for org_key in ctx.orgs:
        org = ctx.orgs[org_key]
        _, created = ProviderNetworkParticipation.objects.update_or_create(
            organization=org,
            network=ctx.legacy_network,
            effective_date=EFFECTIVE_START,
            defaults={
                'status': ProviderNetworkParticipation.Status.IN_NETWORK,
                'network_new': ctx.network,
            },
        )
        if created:
            _bump('ProviderNetworkParticipation')

    for fac in ctx.facilities.values():
        _, created = FacilityNetworkParticipation.objects.update_or_create(
            facility=fac,
            network=ctx.legacy_network,
            effective_date=EFFECTIVE_START,
            defaults={'status': 'IN_NETWORK'},
        )
        if created:
            _bump('FacilityNetworkParticipation')


def _upsert_providers(roster_path: Path, ctx: AgreementContext) -> None:
    rows = _load_csv(roster_path)
    specialty_cache: dict[str, RefSpecialty | None] = {}

    for row in rows:
        org_key = row['org_key'].strip()
        org = ctx.orgs.get(org_key)
        if org is None:
            raise ValueError(f"Unknown org_key {org_key!r} in provider roster")

        spec_code = (row.get('specialty_code') or '').strip()
        if spec_code not in specialty_cache:
            specialty_cache[spec_code] = (
                RefSpecialty.objects.filter(specialty_code=spec_code).first()
                if spec_code
                else None
            )
        specialty = specialty_cache[spec_code]

        effective_date = _parse_date(row.get('effective_date')) or EFFECTIVE_START
        provider, created = Provider.objects.update_or_create(
            npi=row['npi'].strip(),
            defaults={
                'first_name': row['first_name'].strip(),
                'last_name': row['last_name'].strip(),
                'credential': (row.get('credential') or '').strip() or None,
                'primary_specialty': specialty,
                'status': (row.get('status') or 'ACTIVE').strip() or 'ACTIVE',
            },
        )
        if created:
            _bump('Provider')

        valid_roles = {choice.value for choice in ProviderAffiliation.Role}
        role = (row.get('role') or 'EMPLOYEE').strip().upper()
        if role not in valid_roles:
            role = ProviderAffiliation.Role.EMPLOYEE

        _, aff_created = ProviderAffiliation.objects.update_or_create(
            provider=provider,
            organization=org,
            effective_date=effective_date,
            defaults={'role': role},
        )
        if aff_created:
            _bump('ProviderAffiliation')


def _upsert_members(members_path: Path, ctx: AgreementContext) -> None:
    assert ctx.product
    rows = _load_csv(members_path)

    for row in rows:
        member, created = Member.objects.update_or_create(
            member_id=row['member_id'].strip(),
            defaults={
                'first_name': (row.get('first_name') or '').strip() or None,
                'last_name': (row.get('last_name') or '').strip() or None,
                'date_of_birth': _parse_date(row.get('date_of_birth')),
                'zip_code': (row.get('zip_code') or '').strip() or None,
            },
        )
        if created:
            _bump('Member')

        product_key = (row.get('product_key') or '').strip()
        if not product_key:
            continue

        if product_key != PRODUCT_CODE:
            raise ValueError(
                f"Unexpected product_key {product_key!r} for member {member.member_id}"
            )

        effective_date = _parse_date(row.get('enrollment_effective')) or EFFECTIVE_START
        termination_date = _parse_date(row.get('enrollment_termination'))

        _, enr_created = Enrollment.objects.update_or_create(
            member=member,
            product=ctx.product,
            effective_date=effective_date,
            defaults={'termination_date': termination_date},
        )
        if enr_created:
            _bump('Enrollment')


def _upsert_contract(ctx: AgreementContext) -> None:
    assert (
        ctx.payer
        and ctx.legacy_network
        and ctx.product
        and ctx.orgs.get('KHS-IDN')
    )
    idn = ctx.orgs['KHS-IDN']

    contract, created = ProviderContract.objects.update_or_create(
        legacy_contract_number=CONTRACT_LEGACY,
        defaults={
            'contract_name': CONTRACT_NAME,
            'status': 'ACTIVE',
            'effective_start_date': EFFECTIVE_START,
            'effective_end_date': None,
            'provider_org': idn,
            'network': ctx.legacy_network,
            'line_of_business': 'COMMERCIAL',
            'contract_origin_type': ProviderContract.ContractOriginType.DIRECT,
            'resolution_priority': 10,
            'payer_org': ctx.payer,
        },
    )
    ctx.contract = contract
    if created:
        _bump('ProviderContract')

    version, v_created = ContractVersion.objects.update_or_create(
        contract=contract,
        version_number=1,
        defaults={
            'effective_start_date': EFFECTIVE_START,
            'effective_end_date': None,
            'status': ContractVersion.VersionStatus.ACTIVE,
        },
    )
    ctx.version = version
    if v_created:
        _bump('ContractVersion')

    _, scope_created = upsert_unified_product_scope(
        contract_id=contract.contract_id,
        product_id=ctx.product.id,
        lob_code='COMMERCIAL',
        effective_date=EFFECTIVE_START,
        termination_date=None,
    )
    if scope_created:
        _bump('ContractScopeUnified')

    # Legacy table kept for deprecation; resolver reads ContractScopeUnified only.
    ContractProductScope.objects.filter(contract=contract, product=ctx.product).delete()

    _, arr_created = ContractArrangement.objects.update_or_create(
        contract=contract,
        name=f'{CONTRACT_LEGACY} Fee Schedule',
        defaults={
            'arrangement_type': ContractArrangement.ArrangementType.FEE_SCHEDULE,
            'claim_type': None,
            'effective_start_date': EFFECTIVE_START,
            'effective_end_date': None,
            'status': ContractVersion.VersionStatus.ACTIVE,
        },
    )
    if arr_created:
        _bump('ContractArrangement')

    for spec in ORG_SPECS:
        org = ctx.orgs[spec['key']]
        _, ce_created = ContractCoveredEntity.objects.update_or_create(
            contract=contract,
            entity_type=ContractCoveredEntity.EntityType.ORG,
            organization=org,
            defaults={
                'is_primary': spec['key'] == 'KHS-IDN',
                'effective_start_date': EFFECTIVE_START,
                'effective_end_date': None,
            },
        )
        if ce_created:
            _bump('ContractCoveredEntity')

    chen = Provider.objects.filter(npi='KEYSTONE-NPI05').first()
    if chen:
        _, ce_created = ContractCoveredEntity.objects.update_or_create(
            contract=contract,
            entity_type=ContractCoveredEntity.EntityType.PROVIDER,
            provider=chen,
            defaults={
                'is_primary': False,
                'effective_start_date': EFFECTIVE_START,
                'effective_end_date': None,
            },
        )
        if ce_created:
            _bump('ContractCoveredEntity')


@transaction.atomic
def seed_agreement_atomic(
    *,
    roster_path: Path | None = None,
    members_path: Path | None = None,
    stdout=None,
) -> dict[str, Any]:
    global _stats
    _stats = {}

    docs = _default_docs_dir()
    roster_path = roster_path or (docs / 'provider_roster.csv')
    members_path = members_path or (docs / 'members.csv')

    if not roster_path.exists():
        raise FileNotFoundError(f'Provider roster not found: {roster_path}')
    if not members_path.exists():
        raise FileNotFoundError(f'Members file not found: {members_path}')

    ctx = AgreementContext()
    _upsert_payer_stack(ctx)
    _upsert_orgs(ctx)
    _upsert_facilities(ctx)
    _upsert_network_participation(ctx)
    _upsert_providers(roster_path, ctx)
    _upsert_members(members_path, ctx)
    _upsert_contract(ctx)

    assert ctx.contract and ctx.version

    if stdout:
        stdout.write(f'\ncontract_id={ctx.contract.contract_id}')
        stdout.write(f'version_id={ctx.version.version_id}')
        stdout.write(f'legacy_contract_number={CONTRACT_LEGACY}')

    return {
        'created_stats': dict(_stats),
        'contract_id': ctx.contract.contract_id,
        'version_id': ctx.version.version_id,
        'legacy_contract_number': CONTRACT_LEGACY,
    }
