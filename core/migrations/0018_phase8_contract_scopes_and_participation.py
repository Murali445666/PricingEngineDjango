# Phase 8: Contract scopes, provider participation, and ClaimHeader fields for resolution

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_contract_methodology_version_uniq"),
    ]

    operations = [
        migrations.CreateModel(
            name="ContractScope",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("line_of_business", models.CharField(blank=True, max_length=50, null=True)),
                ("site_of_service", models.CharField(blank=True, max_length=20, null=True)),
                ("priority", models.IntegerField(default=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "contract",
                    models.ForeignKey(
                        db_column="contract_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scopes",
                        to="core.providercontract",
                    ),
                ),
                (
                    "geo",
                    models.ForeignKey(
                        blank=True,
                        db_column="geo_id",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contract_scopes",
                        to="core.refgeoindex",
                    ),
                ),
                (
                    "specialty_code",
                    models.ForeignKey(
                        blank=True,
                        db_column="specialty_code",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contract_scopes",
                        to="core.refspecialty",
                        to_field="specialty_code",
                    ),
                ),
            ],
            options={
                "db_table": "contract_scopes",
                "ordering": ["contract", "priority"],
            },
        ),
        migrations.AddIndex(
            model_name="contractscope",
            index=models.Index(
                fields=["contract", "priority"],
                name="scope_contract_priority_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="contractscope",
            index=models.Index(
                fields=["line_of_business", "specialty_code", "site_of_service", "geo"],
                name="scope_dims_idx",
            ),
        ),
        migrations.CreateModel(
            name="ContractProviderParticipation",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("npi", models.CharField(blank=True, max_length=15, null=True)),
                ("effective_start_date", models.DateField()),
                ("effective_end_date", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "contract",
                    models.ForeignKey(
                        db_column="contract_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="participations",
                        to="core.providercontract",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        db_column="organization_id",
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contract_participations",
                        to="core.providerorganization",
                    ),
                ),
            ],
            options={
                "db_table": "contract_provider_participations",
                "ordering": ["contract", "-effective_start_date"],
            },
        ),
        migrations.AddConstraint(
            model_name="contractproviderparticipation",
            constraint=models.CheckConstraint(
                condition=models.Q(organization__isnull=False) | models.Q(npi__isnull=False),
                name="participation_org_or_npi",
            ),
        ),
        migrations.AddIndex(
            model_name="contractproviderparticipation",
            index=models.Index(
                fields=["contract", "organization", "npi"],
                name="part_cntr_org_npi_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="contractproviderparticipation",
            index=models.Index(
                fields=["effective_start_date", "effective_end_date"],
                name="participation_dates_idx",
            ),
        ),
        migrations.AlterField(
            model_name="claimheader",
            name="contract",
            field=models.ForeignKey(
                blank=True,
                db_column="contract_id",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="claims",
                to="core.providercontract",
            ),
        ),
        migrations.AddField(
            model_name="claimheader",
            name="provider_org",
            field=models.ForeignKey(
                blank=True,
                null=True,
                db_column="provider_org_id",
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="claim_headers",
                to="core.providerorganization",
            ),
        ),
        migrations.AddField(
            model_name="claimheader",
            name="npi",
            field=models.CharField(blank=True, max_length=15, null=True),
        ),
        migrations.AddField(
            model_name="claimheader",
            name="site_of_service",
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name="claimheader",
            name="geo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                db_column="geo_id",
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="claim_headers",
                to="core.refgeoindex",
            ),
        ),
    ]
