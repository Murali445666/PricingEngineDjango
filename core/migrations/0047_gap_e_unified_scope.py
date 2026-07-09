# Gap E — unified contract scope + idempotent backfill

from django.db import migrations, models
import django.db.models.deletion


def backfill_unified_scopes(apps, schema_editor):
    ContractScope = apps.get_model('core', 'ContractScope')
    ContractProductScope = apps.get_model('core', 'ContractProductScope')
    Unified = apps.get_model('core', 'ContractScopeUnified')

    for scope in ContractScope.objects.all().iterator():
        Unified.objects.get_or_create(
            migration_source='CONTRACT_SCOPE',
            migration_source_id=scope.id,
            defaults={
                'contract_id': scope.contract_id,
                'lob_code': scope.line_of_business or None,
                'product_id': None,
                'specialty_code_id': scope.specialty_code_id,
                'site_of_service': scope.site_of_service,
                'geo_id': scope.geo_id,
                'effective_date': None,
                'termination_date': None,
                'priority': scope.priority,
            },
        )

    for ps in ContractProductScope.objects.all().iterator():
        Unified.objects.get_or_create(
            migration_source='PRODUCT_SCOPE',
            migration_source_id=ps.id,
            defaults={
                'contract_id': ps.contract_id,
                'lob_code': ps.lob_code,
                'product_id': ps.product_id,
                'specialty_code_id': None,
                'site_of_service': None,
                'geo_id': None,
                'effective_date': ps.effective_date,
                'termination_date': ps.termination_date,
                'priority': 100,
            },
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0046_gap_b_contract_escalator'),
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContractScopeUnified',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('lob_code', models.CharField(blank=True, max_length=50, null=True)),
                ('site_of_service', models.CharField(blank=True, max_length=20, null=True)),
                ('effective_date', models.DateField(blank=True, null=True)),
                ('termination_date', models.DateField(blank=True, null=True)),
                ('priority', models.IntegerField(default=100)),
                (
                    'migration_source',
                    models.CharField(
                        choices=[
                            ('CONTRACT_SCOPE', 'ContractScope'),
                            ('PRODUCT_SCOPE', 'ContractProductScope'),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ('migration_source_id', models.BigIntegerField(db_index=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'contract',
                    models.ForeignKey(
                        db_column='contract_id',
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='unified_scopes',
                        to='core.providercontract',
                    ),
                ),
                (
                    'geo',
                    models.ForeignKey(
                        blank=True,
                        db_column='geo_id',
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='unified_contract_scopes',
                        to='core.refgeoindex',
                    ),
                ),
                (
                    'product',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to='products.product',
                    ),
                ),
                (
                    'specialty_code',
                    models.ForeignKey(
                        blank=True,
                        db_column='specialty_code',
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='unified_contract_scopes',
                        to='core.refspecialty',
                        to_field='specialty_code',
                    ),
                ),
            ],
            options={
                'db_table': 'contract_scopes_unified',
                'ordering': ['contract', 'priority', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='contractscopeunified',
            constraint=models.UniqueConstraint(
                fields=('migration_source', 'migration_source_id'),
                name='contract_scope_unified_source_uniq',
            ),
        ),
        migrations.AddIndex(
            model_name='contractscopeunified',
            index=models.Index(fields=['contract', 'lob_code'], name='cs_unified_cntr_lob_idx'),
        ),
        migrations.AddIndex(
            model_name='contractscopeunified',
            index=models.Index(fields=['contract', 'product'], name='cs_unified_cntr_prod_idx'),
        ),
        migrations.RunPython(backfill_unified_scopes, noop_reverse),
    ]
