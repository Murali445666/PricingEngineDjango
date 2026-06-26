# Phase 7: Contract stop-loss rules and ClaimLine.cost_amount

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_phase6_hardening_threshold_scope_and_constraint"),
    ]

    operations = [
        migrations.AddField(
            model_name="claimline",
            name="cost_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=0,
                help_text="Cost for this line; used for stop-loss (Phase 7).",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="ContractStopLossRule",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("cost_threshold", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "reimbursement_percentage",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Percentage of cost paid above threshold",
                        max_digits=5,
                    ),
                ),
                ("priority", models.IntegerField(default=0)),
                ("effective_start_date", models.DateField()),
                ("effective_end_date", models.DateField(blank=True, null=True)),
                (
                    "contract",
                    models.ForeignKey(
                        db_column="contract_id",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stop_loss_rules",
                        to="core.providercontract",
                    ),
                ),
            ],
            options={
                "db_table": "contract_stop_loss_rules",
                "ordering": ["contract", "-priority", "effective_start_date"],
            },
        ),
        migrations.AddConstraint(
            model_name="contractstoplossrule",
            constraint=models.CheckConstraint(
                condition=models.Q(reimbursement_percentage__gt=0)
                & models.Q(reimbursement_percentage__lte=100),
                name="stoploss_reimbursement_pct_range",
            ),
        ),
        migrations.AddIndex(
            model_name="contractstoplossrule",
            index=models.Index(
                fields=["contract", "-priority"],
                name="stoploss_contract_priority_idx",
            ),
        ),
    ]
