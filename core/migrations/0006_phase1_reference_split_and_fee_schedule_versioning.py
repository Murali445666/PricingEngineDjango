# Phase 1: Reference table split (CPT/HCPCS vs RVUs) and fee schedule versioning
# Plan: schema_upgrade_for_enterprise_simulation_6d0bd9b3.plan.md

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_merge_20260220_2018'),
    ]

    operations = [
        migrations.CreateModel(
            name='RefCptHcpcsCode',
            fields=[
                ('code', models.CharField(max_length=20, primary_key=True, serialize=False)),
                ('code_type', models.CharField(max_length=8)),
                ('description', models.CharField(blank=True, max_length=255, null=True)),
                ('status_indicator', models.CharField(blank=True, max_length=10, null=True)),
                ('effective_year', models.IntegerField()),
            ],
            options={
                'db_table': 'ref_cpt_hcpcs_codes',
                'managed': True,
            },
        ),
        migrations.CreateModel(
            name='RefMpfsRvu',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('code', models.CharField(db_index=True, max_length=20)),
                ('year', models.IntegerField(db_index=True)),
                ('work_rvu', models.DecimalField(decimal_places=4, default=0, max_digits=10)),
                ('pe_rvu', models.DecimalField(decimal_places=4, default=0, max_digits=10)),
                ('mp_rvu', models.DecimalField(decimal_places=4, default=0, max_digits=10)),
                ('total_rvu', models.DecimalField(blank=True, decimal_places=4, max_digits=10, null=True)),
                ('status_indicator', models.CharField(blank=True, max_length=10, null=True)),
            ],
            options={
                'db_table': 'ref_mpfs_rvu',
                'managed': True,
            },
        ),
        migrations.AddConstraint(
            model_name='refmpfsrvu',
            constraint=models.UniqueConstraint(
                fields=('code', 'year'),
                name='ref_mpfs_rvu_code_year_uniq',
            ),
        ),
        migrations.AddField(
            model_name='feeschedule',
            name='effective_year',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='feeschedule',
            name='effective_start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='feeschedule',
            name='effective_end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='feeschedule',
            name='schedule_type',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='feeschedule',
            name='source',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='feeschedule',
            name='geo',
            field=models.ForeignKey(
                blank=True,
                db_column='geo_id',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='fee_schedules',
                to='core.refgeoindex',
            ),
        ),
        migrations.AddField(
            model_name='feeschedulerate',
            name='effective_start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='feeschedulerate',
            name='effective_end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='feeschedulerate',
            name='year',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
