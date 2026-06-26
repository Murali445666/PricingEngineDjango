# Phase 5B: Claim Header and Claim Line (persistent claim for bulk simulation)
# Plan: schema_upgrade_for_enterprise_simulation_6d0bd9b3.plan.md

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_phase2b_contract_methodology'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClaimHeader',
            fields=[
                ('claim_id', models.BigAutoField(primary_key=True, serialize=False)),
                ('member_id', models.CharField(blank=True, max_length=64, null=True)),
                ('service_date', models.DateField()),
                ('claim_type', models.CharField(blank=True, max_length=20, null=True)),
                ('drg_code', models.CharField(blank=True, max_length=20, null=True)),
                ('line_of_business', models.CharField(blank=True, max_length=50, null=True)),
                ('pricing_date', models.DateField(blank=True, null=True)),
                ('contract', models.ForeignKey(
                    db_column='contract_id',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='claims',
                    to='core.providercontract',
                )),
            ],
            options={
                'db_table': 'claim_headers',
                'managed': True,
                'ordering': ['-service_date'],
            },
        ),
        migrations.CreateModel(
            name='ClaimLine',
            fields=[
                ('line_id', models.BigAutoField(primary_key=True, serialize=False)),
                ('procedure_code', models.CharField(max_length=20)),
                ('modifiers', models.JSONField(blank=True, default=list)),
                ('billed_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('units', models.IntegerField(default=1)),
                ('sequence', models.IntegerField(default=0)),
                ('claim', models.ForeignKey(
                    db_column='claim_id',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lines',
                    to='core.claimheader',
                )),
            ],
            options={
                'db_table': 'claim_lines',
                'managed': True,
                'ordering': ['claim', 'sequence', 'line_id'],
            },
        ),
    ]
