# Phase E: Claim-level methodology — FacilityBaseRate, CaseRateDefinition; ContractVersion.claim_level_drg_enabled.
# Run: python manage.py migrate core

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0028_phase_d_reference_only_pricing'),
    ]

    operations = [
        migrations.AddField(
            model_name='contractversion',
            name='claim_level_drg_enabled',
            field=models.BooleanField(db_column='claim_level_drg_enabled', default=False),
        ),
        migrations.CreateModel(
            name='FacilityBaseRate',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('facility_id', models.IntegerField(blank=True, null=True)),
                ('rate_type', models.CharField(max_length=20)),
                ('base_rate', models.DecimalField(decimal_places=2, max_digits=12)),
                ('effective_start_date', models.DateField()),
                ('effective_end_date', models.DateField(blank=True, null=True)),
                ('contract', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='contract_id',
                    related_name='facility_base_rates',
                    to='core.providercontract',
                )),
                ('version', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='version_id',
                    related_name='facility_base_rates',
                    to='core.contractversion',
                )),
            ],
            options={
                'db_table': 'facility_base_rates',
                'managed': True,
            },
        ),
        migrations.AddIndex(
            model_name='facilitybaserate',
            index=models.Index(
                fields=['contract', 'version', 'facility_id', 'rate_type', 'effective_start_date', 'effective_end_date'],
                name='fbr_cv_fac_type_dates_idx',
            ),
        ),
        migrations.CreateModel(
            name='CaseRateDefinition',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('case_rate_code', models.CharField(max_length=50)),
                ('lump_sum_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('effective_start_date', models.DateField()),
                ('effective_end_date', models.DateField(blank=True, null=True)),
                ('contract', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='contract_id',
                    related_name='case_rate_definitions',
                    to='core.providercontract',
                )),
                ('version', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='version_id',
                    related_name='case_rate_definitions',
                    to='core.contractversion',
                )),
            ],
            options={
                'db_table': 'case_rate_definitions',
                'managed': True,
            },
        ),
        migrations.AddIndex(
            model_name='caseratedefinition',
            index=models.Index(
                fields=['contract', 'version', 'effective_start_date', 'effective_end_date'],
                name='case_rate_cv_dates_idx',
            ),
        ),
    ]
