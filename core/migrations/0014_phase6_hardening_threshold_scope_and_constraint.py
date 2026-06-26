# Phase 6 Hardening: threshold_scope rename, choices, DB constraint, index

from django.db import migrations, models


def migrate_scope_values(apps, schema_editor):
    """Migrate threshold_scope from per_claim/per_line to PER_CLAIM/PER_LINE."""
    ContractOutlierRule = apps.get_model("core", "ContractOutlierRule")
    ContractOutlierRule.objects.filter(threshold_scope="per_claim").update(threshold_scope="PER_CLAIM")
    ContractOutlierRule.objects.filter(threshold_scope="per_line").update(threshold_scope="PER_LINE")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_alter_contractoutlierrule_options_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="contractoutlierrule",
            old_name="threshold_type",
            new_name="threshold_scope",
        ),
        migrations.RunPython(migrate_scope_values, noop),
        migrations.AlterField(
            model_name="contractoutlierrule",
            name="threshold_scope",
            field=models.CharField(
                choices=[("PER_CLAIM", "Per Claim"), ("PER_LINE", "Per Line")],
                default="PER_CLAIM",
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name="contractoutlierrule",
            constraint=models.CheckConstraint(
                condition=models.Q(reimbursement_percentage__isnull=False)
                | models.Q(cost_to_charge_ratio__isnull=False),
                name="outlier_requires_payment_method",
            ),
        ),
        migrations.AddIndex(
            model_name="contractoutlierrule",
            index=models.Index(
                fields=["contract", "-priority"],
                name="outlier_contract_priority_idx",
            ),
        ),
    ]
