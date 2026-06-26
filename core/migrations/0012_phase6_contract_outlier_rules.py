# Phase 6: Contract outlier rules and stop-loss precedence

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_phase3_phase4_icd10_asp_revenue_specialty'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContractOutlierRule',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('threshold_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('threshold_type', models.CharField(choices=[('per_claim', 'Per claim'), ('per_line', 'Per line')], default='per_claim', max_length=20)),
                ('reimbursement_percentage', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('cost_to_charge_ratio', models.DecimalField(blank=True, decimal_places=4, max_digits=8, null=True)),
                ('priority', models.IntegerField(default=0)),
                ('effective_start_date', models.DateField(default='1900-01-01')),
                ('effective_end_date', models.DateField(blank=True, null=True)),
                ('contract', models.ForeignKey(db_column='contract_id', on_delete=django.db.models.deletion.CASCADE, related_name='outlier_rules', to='core.providercontract')),
            ],
            options={
                'db_table': 'contract_outlier_rules',
                'managed': True,
                'ordering': ['contract', 'priority', 'effective_start_date'],
            },
        ),
    ]
