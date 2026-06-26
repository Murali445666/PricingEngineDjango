# Phase B: ContractTerm and PricingRule.contract_term_id
# Run: python manage.py migrate core
# If you have no migrations yet, run: python manage.py makemigrations core
# then migrate. Otherwise ensure 0001_initial exists and this is 0002.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),  # must exist; create with makemigrations if needed
    ]

    operations = [
        migrations.CreateModel(
            name='ContractTerm',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=150)),
                ('multiplier', models.DecimalField(decimal_places=4, default=1.0, max_digits=10)),
                ('effective_start_date', models.DateField()),
                ('effective_end_date', models.DateField(blank=True, null=True)),
                ('contract', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='contract_id',
                    related_name='contract_terms',
                    to='core.providercontract',
                )),
                ('version', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    db_column='version_id',
                    related_name='contract_terms',
                    to='core.contractversion',
                )),
            ],
            options={
                'db_table': 'contract_terms',
                'managed': True,
            },
        ),
        migrations.AddIndex(
            model_name='contractterm',
            index=models.Index(
                fields=['contract', 'version', 'effective_start_date', 'effective_end_date'],
                name='contract_terms_cv_dates_idx',
            ),
        ),
        migrations.AddField(
            model_name='pricingrule',
            name='contract_term',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                db_column='contract_term_id',
                related_name='pricing_rules',
                to='core.contractterm',
            ),
        ),
    ]
