# Generated manually for Stage 1 — extend ProviderOrganization (additive only)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0032_step14a_tiered_resolution'),
    ]

    operations = [
        migrations.AddField(
            model_name='providerorganization',
            name='npi_type',
            field=models.CharField(
                blank=True,
                choices=[('1', 'Type 1 - Individual'), ('2', 'Type 2 - Organization')],
                max_length=1,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='providerorganization',
            name='org_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('SOLO', 'Solo Practice'),
                    ('GROUP', 'Group Practice'),
                    ('IDS', 'Integrated Delivery System'),
                    ('HEALTH_SYSTEM', 'Health System'),
                    ('FACILITY', 'Facility/Hospital'),
                ],
                max_length=30,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='providerorganization',
            name='parent_org',
            field=models.ForeignKey(
                blank=True,
                db_column='parent_org_id',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='child_orgs',
                to='core.providerorganization',
            ),
        ),
    ]
