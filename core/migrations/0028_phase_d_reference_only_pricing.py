# Phase D: Reference-only pricing — PerDiemRate, ModifierAdjustment, ContractFlatRateOverride;
# ContractMethodology.contract_term_id; PricingRule.per_diem_rate_id, flat_rate_override_id.
# Run: python manage.py migrate core

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0027_phase_c_code_group'),
    ]

    operations = [
        migrations.CreateModel(
            name='PerDiemRate',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('rate_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('effective_start_date', models.DateField()),
                ('effective_end_date', models.DateField(blank=True, null=True)),
                ('contract', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='contract_id',
                    related_name='per_diem_rates',
                    to='core.providercontract',
                )),
                ('version', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='version_id',
                    related_name='per_diem_rates',
                    to='core.contractversion',
                )),
            ],
            options={
                'db_table': 'per_diem_rates',
                'managed': True,
            },
        ),
        migrations.AddIndex(
            model_name='perdiemrate',
            index=models.Index(
                fields=['contract', 'version', 'effective_start_date', 'effective_end_date'],
                name='per_diem_rates_cv_dates_idx',
            ),
        ),
        migrations.CreateModel(
            name='ModifierAdjustment',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('modifier_code', models.CharField(max_length=5)),
                ('adjustment_type', models.CharField(
                    choices=[('PERCENT', 'Percentage')],
                    default='PERCENT',
                    max_length=20,
                )),
                ('adjustment_value', models.DecimalField(decimal_places=2, max_digits=8)),
                ('effective_start_date', models.DateField()),
                ('effective_end_date', models.DateField(blank=True, null=True)),
                ('contract', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='contract_id',
                    related_name='modifier_adjustments',
                    to='core.providercontract',
                )),
                ('version', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='version_id',
                    related_name='modifier_adjustments',
                    to='core.contractversion',
                )),
            ],
            options={
                'db_table': 'modifier_adjustments',
                'managed': True,
            },
        ),
        migrations.AddIndex(
            model_name='modifieradjustment',
            index=models.Index(
                fields=['contract', 'version', 'modifier_code', 'effective_start_date', 'effective_end_date'],
                name='mod_adj_cv_code_dates_idx',
            ),
        ),
        migrations.CreateModel(
            name='ContractFlatRateOverride',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('procedure_code', models.CharField(blank=True, max_length=20, null=True)),
                ('rate_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('effective_start_date', models.DateField()),
                ('effective_end_date', models.DateField(blank=True, null=True)),
                ('contract', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='contract_id',
                    related_name='flat_rate_overrides',
                    to='core.providercontract',
                )),
                ('version', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='version_id',
                    related_name='flat_rate_overrides',
                    to='core.contractversion',
                )),
            ],
            options={
                'db_table': 'contract_flat_rate_overrides',
                'managed': True,
            },
        ),
        migrations.AddIndex(
            model_name='contractflatrateoverride',
            index=models.Index(
                fields=['contract', 'version', 'effective_start_date', 'effective_end_date'],
                name='flat_rate_ov_cv_dates_idx',
            ),
        ),
        migrations.AddField(
            model_name='contractmethodology',
            name='contract_term',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                db_column='contract_term_id',
                related_name='contract_methodologies',
                to='core.contractterm',
            ),
        ),
        migrations.AddField(
            model_name='pricingrule',
            name='per_diem_rate',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                db_column='per_diem_rate_id',
                related_name='pricing_rules',
                to='core.perdiemrate',
            ),
        ),
        migrations.AddField(
            model_name='pricingrule',
            name='flat_rate_override',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                db_column='flat_rate_override_id',
                related_name='pricing_rules',
                to='core.contractflatrateoverride',
            ),
        ),
    ]
