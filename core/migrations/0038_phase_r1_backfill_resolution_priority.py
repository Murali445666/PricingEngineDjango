# Phase R1: backfill resolution_priority from contract_origin_type.

from django.db import migrations

PRIORITY = {'DIRECT': 10, 'DELEGATED': 15, 'LEASED': 20}


def backfill_resolution_priority(apps, schema_editor):
    ProviderContract = apps.get_model('core', 'ProviderContract')
    for contract in ProviderContract.objects.all().iterator():
        contract.resolution_priority = PRIORITY.get(contract.contract_origin_type, 10)
        contract.save(update_fields=['resolution_priority'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0037_phase_r1_schema_foundation'),
    ]

    operations = [
        migrations.RunPython(backfill_resolution_priority, noop_reverse),
    ]
