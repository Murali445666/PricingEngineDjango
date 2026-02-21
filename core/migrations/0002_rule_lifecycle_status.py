# Generated manually for Phase 3 Segment 3: Rule Lifecycle

from django.db import migrations, models


def populate_status_from_is_active(apps, schema_editor):
    PricingRule = apps.get_model('core', 'PricingRule')
    for rule in PricingRule.objects.all():
        rule.status = 'ACTIVE' if rule.is_active == 1 else 'RETIRED'
        rule.save(update_fields=['status'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricingrule',
            name='status',
            field=models.CharField(
                choices=[('DRAFT', 'Draft'), ('ACTIVE', 'Active'), ('RETIRED', 'Retired')],
                db_column='status',
                default='DRAFT',
                max_length=20,
            ),
            preserve_default=True,
        ),
        migrations.RunPython(populate_status_from_is_active, noop_reverse),
        migrations.RemoveField(
            model_name='pricingrule',
            name='is_active',
        ),
    ]
