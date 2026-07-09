# Phase C3: idempotent backfill of ContractCoveredEntity from existing contract data.

from django.db import migrations


def backfill_covered_entities(apps, schema_editor):
    ProviderContract = apps.get_model('core', 'ProviderContract')
    ContractProviderParticipation = apps.get_model('core', 'ContractProviderParticipation')
    ContractCoveredEntity = apps.get_model('core', 'ContractCoveredEntity')
    Provider = apps.get_model('providers', 'Provider')

    for contract in ProviderContract.objects.all().iterator():
        ContractCoveredEntity.objects.get_or_create(
            contract=contract,
            entity_type='ORG',
            organization_id=contract.provider_org_id,
            is_primary=True,
            defaults={
                'effective_start_date': contract.effective_start_date,
                'effective_end_date': contract.effective_end_date,
            },
        )

        for part in ContractProviderParticipation.objects.filter(contract=contract).iterator():
            if part.organization_id:
                if part.organization_id == contract.provider_org_id:
                    continue
                ContractCoveredEntity.objects.get_or_create(
                    contract=contract,
                    entity_type='ORG',
                    organization_id=part.organization_id,
                    is_primary=False,
                    effective_start_date=part.effective_start_date,
                    defaults={
                        'effective_end_date': part.effective_end_date,
                    },
                )
            elif part.npi and str(part.npi).strip():
                provider = Provider.objects.filter(npi=str(part.npi).strip()).first()
                if provider is None:
                    continue
                ContractCoveredEntity.objects.get_or_create(
                    contract=contract,
                    entity_type='PROVIDER',
                    provider_id=provider.id,
                    effective_start_date=part.effective_start_date,
                    defaults={
                        'is_primary': False,
                        'effective_end_date': part.effective_end_date,
                    },
                )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0041_phase_c3_covered_entity'),
    ]

    operations = [
        migrations.RunPython(backfill_covered_entities, noop_reverse),
    ]
