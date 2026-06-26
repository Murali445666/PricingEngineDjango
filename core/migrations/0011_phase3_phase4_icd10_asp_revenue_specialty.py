# Phase 3: ICD-10-CM, ICD-10-PCS, ASP pricing. Phase 4: Revenue codes, specialties, ProviderOrganization.primary_specialty

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_phase7_indexes_and_performance'),
    ]

    operations = [
        # Phase 3: ICD-10 and ASP reference tables
        migrations.CreateModel(
            name='RefIcd10Cm',
            fields=[
                ('diagnosis_code', models.CharField(max_length=20, primary_key=True, serialize=False)),
                ('description', models.CharField(blank=True, max_length=500, null=True)),
                ('billable_flag', models.BooleanField(default=True)),
                ('effective_year', models.IntegerField(db_index=True)),
            ],
            options={
                'db_table': 'ref_icd10_cm',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='RefIcd10Pcs',
            fields=[
                ('procedure_code', models.CharField(max_length=20, primary_key=True, serialize=False)),
                ('description', models.CharField(blank=True, max_length=500, null=True)),
                ('section', models.CharField(blank=True, max_length=20, null=True)),
                ('body_system', models.CharField(blank=True, max_length=50, null=True)),
                ('year', models.IntegerField(db_index=True)),
            ],
            options={
                'db_table': 'ref_icd10_pcs',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='RefAspPricing',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('hcpcs_code', models.CharField(db_index=True, max_length=20)),
                ('quarter', models.CharField(db_index=True, max_length=10)),
                ('asp', models.DecimalField(decimal_places=4, max_digits=12)),
                ('payment_limit', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
            ],
            options={
                'db_table': 'ref_asp_pricing',
                'managed': True,
            },
        ),
        migrations.AddConstraint(
            model_name='refasppricing',
            constraint=models.UniqueConstraint(fields=('hcpcs_code', 'quarter'), name='asp_hcpcs_quarter_uniq'),
        ),
        # Phase 4: Revenue codes and specialties
        migrations.CreateModel(
            name='RefRevenueCode',
            fields=[
                ('revenue_code', models.CharField(max_length=20, primary_key=True, serialize=False)),
                ('description', models.CharField(blank=True, max_length=255, null=True)),
                ('category', models.CharField(blank=True, max_length=50, null=True)),
            ],
            options={
                'db_table': 'ref_revenue_codes',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='RefSpecialty',
            fields=[
                ('specialty_code', models.CharField(max_length=20, primary_key=True, serialize=False)),
                ('description', models.CharField(blank=True, max_length=255, null=True)),
            ],
            options={
                'db_table': 'ref_specialties',
                'managed': True,
            },
        ),
        migrations.AddField(
            model_name='providerorganization',
            name='primary_specialty',
            field=models.ForeignKey(
                blank=True,
                db_column='primary_specialty_id',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='organizations',
                to='core.refspecialty',
            ),
        ),
    ]
