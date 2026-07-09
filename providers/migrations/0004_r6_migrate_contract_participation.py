# Phase R6: mirror ContractProviderParticipation into ProviderNetworkParticipation.

from django.db import migrations


def migrate_participation_to_network(apps, schema_editor):
    ContractProviderParticipation = apps.get_model(
        'core', 'ContractProviderParticipation'
    )
    ProviderNetworkParticipation = apps.get_model(
        'providers', 'ProviderNetworkParticipation'
    )

    for part in ContractProviderParticipation.objects.select_related('contract').iterator():
        if not part.organization_id:
            continue
        network_id = part.contract.network_id
        exists = ProviderNetworkParticipation.objects.filter(
            organization_id=part.organization_id,
            network_id=network_id,
            contract_id=part.contract_id,
            effective_date=part.effective_start_date,
        ).exists()
        if exists:
            continue
        ProviderNetworkParticipation.objects.create(
            organization_id=part.organization_id,
            network_id=network_id,
            contract_id=part.contract_id,
            participation_source='DIRECT_CONTRACT',
            status='IN_NETWORK',
            effective_date=part.effective_start_date,
            termination_date=part.effective_end_date,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0038_phase_r1_backfill_resolution_priority'),
        ('providers', '0003_phase_r1_schema_foundation'),
    ]

    operations = [
        migrations.RunPython(migrate_participation_to_network, noop_reverse),
    ]
