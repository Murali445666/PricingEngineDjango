# Phase 7: Indexes and performance (resolver + bulk simulation)
# Index names kept under 30 chars for MySQL.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_phase5b_claim_header_and_line'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='pricingrule',
            index=models.Index(
                fields=['contract', 'effective_start_date', 'effective_end_date'],
                name='rule_cntr_dates_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='pricingrule',
            index=models.Index(
                fields=['contract', 'claim_type', 'specificity_score'],
                name='rule_claim_spec_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='pricingrulecondition',
            index=models.Index(fields=['pricing_rule'], name='cond_rule_id_idx'),
        ),
        migrations.AddIndex(
            model_name='feeschedulerate',
            index=models.Index(fields=['fee_schedule', 'code_id'], name='fs_rates_fs_code_idx'),
        ),
        migrations.AddIndex(
            model_name='feeschedulerate',
            index=models.Index(
                fields=['code_id', 'effective_start_date', 'effective_end_date'],
                name='fs_rates_code_dates_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='refdrg',
            index=models.Index(fields=['drg_code', 'year'], name='ref_drg_code_year_idx'),
        ),
        migrations.AddIndex(
            model_name='refapc',
            index=models.Index(fields=['apc_code', 'year'], name='ref_apc_code_year_idx'),
        ),
    ]
