# Phase 7: Contract versioning, carve-outs, base rates; version_id on methodologies, rules, outlier, stop-loss

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_phase7_contract_stop_loss_rules"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContractVersion",
            fields=[
                ("version_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("version_number", models.IntegerField()),
                ("effective_start_date", models.DateField()),
                ("effective_end_date", models.DateField(blank=True, null=True)),
                ("status", models.CharField(default="ACTIVE", max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "contract",
                    models.ForeignKey(
                        db_column="contract_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="core.providercontract",
                    ),
                ),
            ],
            options={
                "db_table": "contract_versions",
                "ordering": ["contract", "-version_number"],
            },
        ),
        migrations.AddField(
            model_name="contractmethodology",
            name="version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                db_column="version_id",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="methodologies",
                to="core.contractversion",
            ),
        ),
        migrations.AddField(
            model_name="pricingrule",
            name="version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                db_column="version_id",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pricing_rules",
                to="core.contractversion",
            ),
        ),
        migrations.AddField(
            model_name="contractoutlierrule",
            name="version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                db_column="version_id",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="outlier_rules",
                to="core.contractversion",
            ),
        ),
        migrations.AddField(
            model_name="contractstoplossrule",
            name="version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                db_column="version_id",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="stop_loss_rules",
                to="core.contractversion",
            ),
        ),
        migrations.CreateModel(
            name="ContractCarveout",
            fields=[
                ("carveout_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("code_type", models.CharField(max_length=20)),
                ("code_value", models.CharField(max_length=20)),
                ("carveout_methodology", models.CharField(max_length=50)),
                (
                    "carveout_percentage",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=6, null=True
                    ),
                ),
                (
                    "version",
                    models.ForeignKey(
                        db_column="version_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="carveouts",
                        to="core.contractversion",
                    ),
                ),
            ],
            options={
                "db_table": "contract_carveouts",
                "ordering": ["version", "code_type", "code_value"],
            },
        ),
        migrations.CreateModel(
            name="ContractBaseRate",
            fields=[
                ("base_rate_id", models.BigAutoField(primary_key=True, serialize=False)),
                ("rate_type", models.CharField(max_length=20)),
                ("base_rate", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "version",
                    models.ForeignKey(
                        db_column="version_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="base_rates",
                        to="core.contractversion",
                    ),
                ),
            ],
            options={
                "db_table": "contract_base_rates",
                "ordering": ["version", "rate_type"],
            },
        ),
    ]
