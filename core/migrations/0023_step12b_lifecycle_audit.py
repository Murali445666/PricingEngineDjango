"""
Step 12b – Rule Lifecycle & Version Audit migration.

Changes:
  - ContractVersion.status: add choices + db_index (column already exists, just alter)
  - ContractCarveout.status: new column
  - ContractCapFloor.status: new column
  - ContractBlendingRule.status: new column
  - ContractVersionAudit: new table
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0022_step10_validation_result"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── ContractVersion: add choices + db_index to existing status column ──
        migrations.AlterField(
            model_name="contractversion",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("ACTIVE", "Active"),
                    ("SUPERSEDED", "Superseded"),
                    ("ARCHIVED", "Archived"),
                ],
                db_index=True,
                default="DRAFT",
                max_length=20,
            ),
        ),

        # ── ContractCarveout: add status ────────────────────────────────────────
        migrations.AddField(
            model_name="contractcarveout",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("ACTIVE", "Active"),
                    ("SUPERSEDED", "Superseded"),
                    ("ARCHIVED", "Archived"),
                ],
                db_index=True,
                default="DRAFT",
                max_length=20,
            ),
        ),

        # ── ContractCapFloor: add status ────────────────────────────────────────
        migrations.AddField(
            model_name="contractcapfloor",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("ACTIVE", "Active"),
                    ("SUPERSEDED", "Superseded"),
                    ("ARCHIVED", "Archived"),
                ],
                db_index=True,
                default="DRAFT",
                max_length=20,
            ),
        ),

        # ── ContractBlendingRule: add status ────────────────────────────────────
        migrations.AddField(
            model_name="contractblendingrule",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("ACTIVE", "Active"),
                    ("SUPERSEDED", "Superseded"),
                    ("ARCHIVED", "Archived"),
                ],
                db_index=True,
                default="DRAFT",
                max_length=20,
            ),
        ),

        # ── ContractVersionAudit: new table ─────────────────────────────────────
        migrations.CreateModel(
            name="ContractVersionAudit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                (
                    "version",
                    models.ForeignKey(
                        db_column="version_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_records",
                        to="core.contractversion",
                    ),
                ),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="changed_by_id",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "change_type",
                    models.CharField(
                        choices=[
                            ("ACTIVATED", "Activated"),
                            ("SUPERSEDED", "Superseded"),
                            ("ARCHIVED", "Archived"),
                            ("DRAFTED", "Drafted"),
                        ],
                        max_length=20,
                    ),
                ),
                ("previous_status", models.CharField(max_length=20)),
                ("new_status", models.CharField(max_length=20)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "db_table": "contract_version_audit",
                "ordering": ["-timestamp"],
                "managed": True,
            },
        ),
        migrations.AddIndex(
            model_name="contractversionaudit",
            index=models.Index(
                fields=["version", "-timestamp"],
                name="ver_audit_version_ts_idx",
            ),
        ),
    ]
