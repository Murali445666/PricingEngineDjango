# Generated for Phase 3 Segment 4: Audit & Versioning

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_rule_lifecycle_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='RuleHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('change_date', models.DateTimeField(auto_now_add=True)),
                ('previous_status', models.CharField(blank=True, max_length=20)),
                ('new_status', models.CharField(max_length=20)),
                ('change_reason', models.TextField(blank=True)),
                ('pricing_rule', models.ForeignKey(db_column='rule_id', on_delete=django.db.models.deletion.CASCADE, related_name='history', to='core.pricingrule')),
            ],
            options={
                'db_table': 'rule_history',
                'ordering': ['-change_date'],
                'managed': True,
            },
        ),
    ]
