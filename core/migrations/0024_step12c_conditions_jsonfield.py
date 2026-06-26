"""
Step 12c-1: Add nullable conditions JSONField to rule tables.

Tables modified (additive only):
  - contract_methodologies
  - contract_carveouts
  - contract_cap_floors
  - contract_blending_rules

All columns are nullable (null=True) so no existing rows are affected.
Default behavior: conditions IS NULL → rule always applies.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0023_step12b_lifecycle_audit"),
    ]

    operations = [
        # ContractMethodology
        migrations.AddField(
            model_name="contractmethodology",
            name="conditions",
            field=models.JSONField(
                blank=True,
                null=True,
                help_text=(
                    "Structured condition JSON; null means always apply. "
                    'Schema: {"operator":"AND","conditions":[{"field":"...","op":"eq","value":"..."}]}'
                ),
            ),
        ),
        # ContractCarveout
        migrations.AddField(
            model_name="contractcarveout",
            name="conditions",
            field=models.JSONField(
                blank=True,
                null=True,
                help_text="Structured condition JSON; null means always apply.",
            ),
        ),
        # ContractCapFloor
        migrations.AddField(
            model_name="contractcapfloor",
            name="conditions",
            field=models.JSONField(
                blank=True,
                null=True,
                help_text="Structured condition JSON; null means always apply.",
            ),
        ),
        # ContractBlendingRule
        migrations.AddField(
            model_name="contractblendingrule",
            name="conditions",
            field=models.JSONField(
                blank=True,
                null=True,
                help_text="Structured condition JSON; null means always apply.",
            ),
        ),
    ]
