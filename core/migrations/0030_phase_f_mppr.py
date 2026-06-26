# Phase F: Cross-line MPPR — MPPRDefinition and MPPRScope.
# Run: python manage.py migrate core

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0029_phase_e_claim_level_methodology'),
    ]

    operations = [
        migrations.CreateModel(
            name='MPPRDefinition',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=150)),
                ('rank_by', models.CharField(
                    choices=[
                        ('ALLOWED_AMOUNT', 'Allowed amount'),
                        ('RVU', 'RVU'),
                        ('FEE_SCHEDULE', 'Fee schedule'),
                    ],
                    default='ALLOWED_AMOUNT',
                    max_length=30,
                )),
                ('primary_pct', models.DecimalField(decimal_places=2, max_digits=6)),
                ('secondary_pct', models.DecimalField(decimal_places=2, max_digits=6)),
                ('tertiary_pct', models.DecimalField(decimal_places=2, max_digits=6)),
                ('effective_start_date', models.DateField()),
                ('effective_end_date', models.DateField(blank=True, null=True)),
                ('contract', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='contract_id',
                    related_name='mppr_definitions',
                    to='core.providercontract',
                )),
                ('version', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='version_id',
                    related_name='mppr_definitions',
                    to='core.contractversion',
                )),
            ],
            options={
                'db_table': 'mppr_definitions',
                'managed': True,
            },
        ),
        migrations.AddIndex(
            model_name='mpprdefinition',
            index=models.Index(
                fields=['contract', 'version', 'effective_start_date', 'effective_end_date'],
                name='mppr_def_cv_dates_idx',
            ),
        ),
        migrations.CreateModel(
            name='MPPRScope',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('procedure_code', models.CharField(blank=True, max_length=20, null=True)),
                ('code_group', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='code_group_id',
                    related_name='mppr_scopes',
                    to='core.codegroup',
                )),
                ('mppr_definition', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='mppr_definition_id',
                    related_name='scopes',
                    to='core.mpprdefinition',
                )),
            ],
            options={
                'db_table': 'mppr_scopes',
                'managed': True,
            },
        ),
    ]
