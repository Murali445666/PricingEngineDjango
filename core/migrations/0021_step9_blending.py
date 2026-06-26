# Step 9: create ContractBlendingRule table for multi-methodology blending.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_step7_carveout_rate_step8_cap_floor"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContractBlendingRule",
            fields=[
                ("blending_rule_id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "blend_type",
                    models.CharField(
                        max_length=20,
                        help_text="ADD or OVERRIDE",
                    ),
                ),
                ("scope", models.CharField(default="CLAIM", max_length=20)),
                (
                    "primary_methodology",
                    models.CharField(
                        default="",
                        max_length=50,
                        help_text="Methodology code this rule targets; empty = apply to all.",
                    ),
                ),
                (
                    "secondary_methodology",
                    models.CharField(
                        default="",
                        max_length=50,
                        help_text="Label for the secondary pricing basis (informational).",
                    ),
                ),
                (
                    "blend_percentage",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=6,
                        help_text="Percentage applied to total_billed for ADD/OVERRIDE computation.",
                    ),
                ),
                ("priority", models.IntegerField(default=0)),
                ("effective_start_date", models.DateField()),
                ("effective_end_date", models.DateField(blank=True, null=True)),
                (
                    "version",
                    models.ForeignKey(
                        db_column="version_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blending_rules",
                        to="core.contractversion",
                    ),
                ),
            ],
            options={
                "db_table": "contract_blending_rules",
                "ordering": ["-priority", "effective_start_date"],
            },
        ),

        migrations.AddIndex(
            model_name="contractblendingrule",
            index=models.Index(
                fields=["version", "-priority"],
                name="blend_version_priority_idx",
            ),
        ),
    ]
