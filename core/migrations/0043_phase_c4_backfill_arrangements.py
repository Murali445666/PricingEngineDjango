# Phase C4: idempotent backfill of ContractArrangement and PricingRule.arrangement.

from django.db import migrations
from django.db.models import Q

METHODOLOGY_ARRANGEMENT = {
    'RBRVS': ('FEE_SCHEDULE', 'RBRVS Fee Schedule'),
    'FLAT_RATE': ('FEE_SCHEDULE', 'Flat Rate'),
    'PERCENT_BILLED': ('FEE_SCHEDULE', 'Percent of Billed'),
    'PCT_BILLED': ('FEE_SCHEDULE', 'Percent of Billed'),
    'DRG': ('DRG_CASE_RATE', 'DRG Case Rate'),
    'PER_DIEM': ('PER_DIEM', 'Per Diem'),
    'APC': ('APC', 'APC'),
    'OPPS': ('APC', 'OPPS/APC'),
    'ANESTHESIA': ('ANESTHESIA', 'Anesthesia'),
    'ASP': ('DRUG_ASP', 'Drug ASP'),
    'DRUG': ('DRUG_ASP', 'Drug ASP'),
}


def backfill_arrangements(apps, schema_editor):
    ProviderContract = apps.get_model('core', 'ProviderContract')
    PricingRule = apps.get_model('core', 'PricingRule')
    ContractArrangement = apps.get_model('core', 'ContractArrangement')

    for contract in ProviderContract.objects.all().iterator():
        raw_codes = (
            PricingRule.objects.filter(contract=contract)
            .values_list('methodology_code', flat=True)
            .distinct()
        )
        seen = set()
        for raw_code in raw_codes:
            code = (raw_code or '').strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            arr_type, base_name = METHODOLOGY_ARRANGEMENT.get(
                code, ('FEE_SCHEDULE', f'{code.title()} Arrangement'),
            )
            arrangement, _ = ContractArrangement.objects.get_or_create(
                contract=contract,
                name=f'{base_name} ({code})',
                arrangement_type=arr_type,
                defaults={
                    'status': 'ACTIVE',
                    'effective_start_date': contract.effective_start_date,
                    'effective_end_date': contract.effective_end_date,
                },
            )
            PricingRule.objects.filter(contract=contract).filter(
                Q(methodology_code__iexact=code),
            ).update(arrangement=arrangement)

        orphan_rules = PricingRule.objects.filter(contract=contract).filter(
            Q(methodology_code__isnull=True) | Q(methodology_code=''),
        )
        if orphan_rules.exists():
            arrangement, _ = ContractArrangement.objects.get_or_create(
                contract=contract,
                name='Default Arrangement (unspecified methodology)',
                arrangement_type='FEE_SCHEDULE',
                defaults={
                    'status': 'ACTIVE',
                    'effective_start_date': contract.effective_start_date,
                    'effective_end_date': contract.effective_end_date,
                },
            )
            orphan_rules.update(arrangement=arrangement)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0042_phase_c3_backfill_covered_entities'),
    ]

    operations = [
        migrations.RunPython(backfill_arrangements, noop_reverse),
    ]
