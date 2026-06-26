# Step 7: add carveout_rate to ContractCarveout for FIXED_RATE carve-outs.
# Step 8: create ContractCapFloor table for claim-level caps and floors.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_mysql_fix_index_and_constraints"),
    ]

    operations = [
        # Step 7: add fixed-dollar rate column to ContractCarveout
        migrations.AddField(
            model_name="contractcarveout",
            name="carveout_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=12,
                null=True,
                help_text="Fixed dollar rate; used when carveout_methodology=FIXED_RATE",
            ),
        ),

        # Step 8: ContractCapFloor table
        migrations.CreateModel(
            name="ContractCapFloor",
            fields=[
                ("cap_floor_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("scope", models.CharField(default="CLAIM", max_length=20)),
                ("cap_type", models.CharField(max_length=20)),
                (
                    "value",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=14,
                        null=True,
                        help_text="Absolute dollar cap or floor value",
                    ),
                ),
                (
                    "percentage",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=6,
                        null=True,
                        help_text="Percentage of billed; used when cap_type=PCT_BILLED_CAP",
                    ),
                ),
                (
                    "code_value",
                    models.CharField(
                        blank=True,
                        max_length=20,
                        null=True,
                        help_text=(
                            "Restrict to this DRG or APC code; "
                            "null = apply to all codes of the scope type"
                        ),
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
                        related_name="cap_floors",
                        to="core.contractversion",
                    ),
                ),
            ],
            options={
                "db_table": "contract_cap_floors",
                "ordering": ["-priority", "effective_start_date"],
            },
        ),

        # Index for fast lookup by version + cap_type
        migrations.AddIndex(
            model_name="contractcapfloor",
            index=models.Index(
                fields=["version", "cap_type"],
                name="capfloor_version_type_idx",
            ),
        ),

        # Index for fast carve-out lookup by version + code
        migrations.AddIndex(
            model_name="contractcarveout",
            index=models.Index(
                fields=["version", "code_type", "code_value"],
                name="carveout_version_code_idx",
            ),
        ),
    ]
