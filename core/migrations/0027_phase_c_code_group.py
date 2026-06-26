# Phase C: CodeGroup and CodeGroupMember for resolver code_group condition

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0026_merge_20260304_2009'),
    ]

    operations = [
        migrations.CreateModel(
            name='CodeGroup',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('code_group_code', models.CharField(max_length=50)),
                ('name', models.CharField(max_length=150)),
                ('effective_start_date', models.DateField()),
                ('effective_end_date', models.DateField(blank=True, null=True)),
                ('contract', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='contract_id',
                    related_name='code_groups',
                    to='core.providercontract',
                )),
                ('version', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='version_id',
                    related_name='code_groups',
                    to='core.contractversion',
                )),
            ],
            options={
                'db_table': 'code_groups',
                'managed': True,
            },
        ),
        migrations.AddIndex(
            model_name='codegroup',
            index=models.Index(
                fields=['contract', 'version', 'effective_start_date', 'effective_end_date'],
                name='code_groups_cv_dates_idx',
            ),
        ),
        migrations.CreateModel(
            name='CodeGroupMember',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('code_id', models.CharField(max_length=20)),
                ('effective_start_date', models.DateField()),
                ('effective_end_date', models.DateField(blank=True, null=True)),
                ('code_group', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='code_group_id',
                    related_name='members',
                    to='core.codegroup',
                )),
            ],
            options={
                'db_table': 'code_group_members',
                'managed': True,
            },
        ),
        migrations.AddIndex(
            model_name='codegroupmember',
            index=models.Index(
                fields=['code_group', 'code_id'],
                name='code_group_members_cg_code_idx',
            ),
        ),
    ]
