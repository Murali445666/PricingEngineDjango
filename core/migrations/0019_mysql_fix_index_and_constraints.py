# MySQL compatibility: remove conditional unique constraints (MySQL does not support partial
# unique indexes). Uniqueness for ContractMethodology enforced in model clean().
# Index name part_cntr_org_npi_idx is already used in 0018 (31-char name would exceed MySQL 30).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_phase8_contract_scopes_and_participation"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="contractmethodology",
            name="contract_methodology_contract_type_date_uniq",
        ),
        migrations.RemoveConstraint(
            model_name="contractmethodology",
            name="contract_methodology_version_type_date_uniq",
        ),
    ]
