# Phase 2: DRG and APC reference tables
# Plan: schema_upgrade_for_enterprise_simulation_6d0bd9b3.plan.md

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_phase1_reference_split_and_fee_schedule_versioning'),
    ]

    operations = [
        migrations.CreateModel(
            name='RefDrg',
            fields=[
                ('drg_code', models.CharField(max_length=20, primary_key=True, serialize=False)),
                ('description', models.CharField(blank=True, max_length=255, null=True)),
                ('relative_weight', models.DecimalField(decimal_places=6, default=0, max_digits=12)),
                ('geometric_mean_los', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('arithmetic_mean_los', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('mdc', models.CharField(blank=True, max_length=10, null=True)),
                ('year', models.IntegerField(db_index=True)),
            ],
            options={
                'db_table': 'ref_drg',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='RefApc',
            fields=[
                ('apc_code', models.CharField(max_length=20, primary_key=True, serialize=False)),
                ('description', models.CharField(blank=True, max_length=255, null=True)),
                ('relative_weight', models.DecimalField(decimal_places=6, default=0, max_digits=12)),
                ('status_indicator', models.CharField(blank=True, max_length=10, null=True)),
                ('payment_rate', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('year', models.IntegerField(db_index=True)),
            ],
            options={
                'db_table': 'ref_apc',
                'managed': True,
            },
        ),
    ]
