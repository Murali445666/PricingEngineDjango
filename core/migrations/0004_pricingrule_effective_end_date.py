# Add effective_end_date to PricingRule

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_rulehistory'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricingrule',
            name='effective_end_date',
            field=models.DateField(blank=True, null=True),
            preserve_default=True,
        ),
    ]
