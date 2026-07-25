"""One-off verification for analyst authoring MVP."""
from __future__ import annotations

import csv
import io
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import django

django.setup()

from django.db import models
from core.models import ContractVersion, PricingRule, ProviderContract  # noqa: E402
from core.services.fee_schedule_import import (  # noqa: E402
    import_fee_schedule_from_rows,
    preview_fee_schedule_import,
)
from core.services.validation_service import ValidationService  # noqa: E402
from core.api.serializers import ContractCreateSerializer  # noqa: E402


def main() -> None:
    legacy = 'MVP-DRAFT-VERIFY-001'
    ProviderContract.objects.filter(legacy_contract_number=legacy).delete()

    ser = ContractCreateSerializer(data={
        'contract_name': 'MVP Draft Verify',
        'legacy_contract_number': legacy,
        'payer_org': 10,
        'provider_org': 'KEYSTONE-IDN',
        'network': 'HIGHMARK-PPO',
        'line_of_business': 'COMMERCIAL',
        'effective_start_date': '2025-04-17',
        'effective_end_date': None,
        'contract_origin_type': 'DIRECT',
        'resolution_priority': 10,
    })
    ser.is_valid(raise_exception=True)
    contract = ser.create(ser.validated_data)
    assert contract.status == 'DRAFT'
    version = ContractVersion.objects.get(contract=contract, version_number=1)
    assert version.status == ContractVersion.VersionStatus.DRAFT
    print(f'OK create DRAFT contract={contract.contract_id} version={version.version_id}')

    resolver_qs = ProviderContract.objects.filter(
        status='ACTIVE',
        effective_start_date__lte=date(2025, 6, 1),
    ).filter(
        models.Q(effective_end_date__isnull=True)
        | models.Q(effective_end_date__gte=date(2025, 6, 1))
    )
    assert not resolver_qs.filter(contract_id=contract.contract_id).exists()
    assert resolver_qs.filter(contract_id=217).exists()
    print(f'OK DRAFT-safe: contract {contract.contract_id} excluded from ACTIVE resolver set (217 present)')

    csv_path = Path('docs/Exhibit_C_Fee_Schedule.csv')
    with csv_path.open(encoding='utf-8', newline='') as handle:
        all_rows = list(csv.DictReader(handle))
    small = all_rows[:5]

    preview = preview_fee_schedule_import(
        contract.contract_id, version.version_id, small, year=2025,
    )
    assert preview.counts['added'] == 5
    print(f'OK preview added={preview.counts["added"]} changed={preview.counts["changed"]}')

    r1 = import_fee_schedule_from_rows(
        contract.contract_id, version.version_id, small, year=2025,
    )
    ids1 = sorted(
        PricingRule.objects.filter(version_id=version.version_id).values_list('rule_id', flat=True)
    )
    r2 = import_fee_schedule_from_rows(
        contract.contract_id, version.version_id, small, year=2025,
    )
    ids2 = sorted(
        PricingRule.objects.filter(version_id=version.version_id).values_list('rule_id', flat=True)
    )
    assert ids1 == ids2, f'rule ids churned: {ids1} vs {ids2}'
    assert r2.rules_created == 0 and r2.rules_updated == 0
    print(f'OK stable ids on re-commit: {ids1}')

    conflicts = ValidationService.validate_contract(217)
    errors = [c for c in conflicts if c.severity == 'ERROR']
    warnings = [c for c in conflicts if c.severity == 'WARNING']
    print(f'OK validate 217: {len(errors)} errors, {len(warnings)} warnings')

    # Price check P1/P5 via service
    from core.engine.service import ClaimPricingService
    from core.engine.types import PricingInput

    contract217 = ProviderContract.objects.get(pk=217)
    version197 = ContractVersion.objects.get(pk=197)
    svc = ClaimPricingService()
    for provider_id, expected in [(None, Decimal('108.12')), (17, Decimal('116.44'))]:
        inp = PricingInput(
            procedure_code='99213',
            billed_amount=Decimal('200'),
            units=1,
            service_date=date(2025, 6, 15),
            claim_type='professional',
            provider_id=provider_id,
        )
        out = svc.price_line(contract217, inp, version=version197)
        assert out.allowed_amount == expected, f'provider={provider_id} got {out.allowed_amount}'
    print('OK contract 217 prices 99213 org=108.12 Chen=116.44')

    ProviderContract.objects.filter(legacy_contract_number=legacy).delete()
    print('DONE all checks passed')


if __name__ == '__main__':
    main()
