# Step 10: create ValidationResult table for contract conflict audit trail.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_step9_blending"),
    ]

    operations = [
        migrations.CreateModel(
            name="ValidationResult",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "contract",
                    models.ForeignKey(
                        db_column="contract_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="validation_results",
                        to="core.providercontract",
                    ),
                ),
                ("validated_at", models.DateTimeField(auto_now_add=True)),
                ("conflict_type", models.CharField(max_length=50)),
                ("severity", models.CharField(max_length=10)),
                ("message", models.TextField()),
                ("affected_objects", models.JSONField(default=list)),
                ("suggested_action", models.TextField(blank=True)),
                ("resolved", models.BooleanField(default=False)),
            ],
            options={
                "db_table": "contract_validation_results",
                "ordering": ["-validated_at", "severity", "conflict_type"],
            },
        ),
        migrations.AddIndex(
            model_name="validationresult",
            index=models.Index(
                fields=["contract", "resolved"],
                name="val_contract_resolved_idx",
            ),
        ),
    ]
