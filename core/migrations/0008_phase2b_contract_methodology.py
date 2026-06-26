# Phase 2B: Contract methodology layer and claim-type
# Plan: schema_upgrade_for_enterprise_simulation_6d0bd9b3.plan.md

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_phase2_drg_apc_reference_tables'),
    ]

    operations = [
        migrations.AddField(
            model_name='providercontract',
            name='line_of_business',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.CreateModel(
            name='ContractMethodology',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('methodology_type', models.CharField(max_length=50)),
                ('base_percentage', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('conversion_factor', models.DecimalField(blank=True, decimal_places=4, max_digits=10, null=True)),
                ('effective_date', models.DateField()),
                ('termination_date', models.DateField(blank=True, null=True)),
                ('priority', models.IntegerField(default=0)),
                ('claim_type', models.CharField(blank=True, max_length=20, null=True)),
                ('site_of_service', models.CharField(blank=True, max_length=50, null=True)),
                ('contract', models.ForeignKey(
                    db_column='contract_id',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='methodologies',
                    to='core.providercontract',
                )),
                ('fee_schedule', models.ForeignKey(
                    blank=True,
                    db_column='fee_schedule_id',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='contract_methodologies',
                    to='core.feeschedule',
                )),
            ],
            options={
                'db_table': 'contract_methodologies',
                'managed': True,
            },
        ),
        migrations.AddConstraint(
            model_name='contractmethodology',
            constraint=models.UniqueConstraint(
                fields=('contract', 'methodology_type', 'effective_date'),
                name='contract_methodology_contract_type_date_uniq',
            ),
        ),
        migrations.AddField(
            model_name='pricingrule',
            name='claim_type',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='pricingrule',
            name='site_of_service',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AlterField(
            model_name='pricingrule',
            name='methodology_code',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
