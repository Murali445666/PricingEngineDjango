# Generated manually for §18 T1.1 + T1.4 amendment workflow.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0048_gap_e_unified_scope_meta'),
    ]

    operations = [
        migrations.AddField(
            model_name='contractversion',
            name='scheduled_activation_date',
            field=models.DateField(blank=True, db_column='scheduled_activation_date', null=True),
        ),
        migrations.AddField(
            model_name='contractamendment',
            name='version',
            field=models.ForeignKey(
                blank=True,
                db_column='version_id',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='amendment',
                to='core.contractversion',
            ),
        ),
        migrations.CreateModel(
            name='ContractVersionSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('snapshot', models.JSONField()),
                ('checksum', models.CharField(max_length=64)),
                (
                    'version',
                    models.OneToOneField(
                        db_column='version_id',
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='config_snapshot',
                        to='core.contractversion',
                    ),
                ),
            ],
            options={
                'db_table': 'contract_version_snapshots',
                'ordering': ['-created_at'],
                'managed': True,
            },
        ),
    ]
