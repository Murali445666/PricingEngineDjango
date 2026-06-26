# ContractMethodology: allow version-scoped and contract-level rows for same (contract, type, date)
# by replacing the single unique constraint with two partial unique constraints.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_phase7_contract_versioning_carveouts_base_rates"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="contractmethodology",
            name="contract_methodology_contract_type_date_uniq",
        ),
        migrations.AddConstraint(
            model_name="contractmethodology",
            constraint=models.UniqueConstraint(
                condition=models.Q(version_id__isnull=True),
                fields=("contract", "methodology_type", "effective_date"),
                name="contract_methodology_contract_type_date_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="contractmethodology",
            constraint=models.UniqueConstraint(
                condition=models.Q(version_id__isnull=False),
                fields=("contract", "version", "methodology_type", "effective_date"),
                name="contract_methodology_version_type_date_uniq",
            ),
        ),
    ]
