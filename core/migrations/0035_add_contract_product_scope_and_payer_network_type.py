# Stage 2 — ContractProductScope and PayerNetwork.network_type (additive only)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0034_remove_contractbaserate_cbr_version_rate_type_idx_and_more'),
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='payernetwork',
            name='network_type',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.CreateModel(
            name='ContractProductScope',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('lob_code', models.CharField(blank=True, max_length=30, null=True)),
                ('effective_date', models.DateField(blank=True, null=True)),
                ('termination_date', models.DateField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'contract',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='product_scopes',
                        to='core.providercontract',
                    ),
                ),
                (
                    'product',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to='products.product',
                    ),
                ),
            ],
            options={
                'db_table': 'contract_product_scopes',
            },
        ),
    ]
