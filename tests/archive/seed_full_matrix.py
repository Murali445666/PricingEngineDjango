from django.core.management.base import BaseCommand
from core.models import (
    ProviderOrganization, PayerNetwork, ProviderContract, 
    PricingRule, PricingRuleCondition, RefProcedureCode, 
    FeeSchedule, FeeScheduleRate, RefModifier
)
from decimal import Decimal
from datetime import date

class Command(BaseCommand):
    help = 'Seeds data for ALL 10 Test Scenarios (DRG, Per Diem, etc.)'

    def handle(self, *args, **kwargs):
        self.stdout.write("🏗️  Building Full Matrix Test Data...")

        # 1. Base Contract Setup
        org, _ = ProviderOrganization.objects.get_or_create(organization_id='ORG-MATRIX', defaults={'name': 'Matrix Health'})
        net, _ = PayerNetwork.objects.get_or_create(network_id='NET-MATRIX', defaults={'payer_org': org})
        contract, _ = ProviderContract.objects.get_or_create(
            legacy_contract_number='CONT-MATRIX-2026',
            defaults={'provider_org': org, 'network': net, 'status': 'ACTIVE', 'effective_start_date': date(2026, 1, 1)}
        )
        fs, _ = FeeSchedule.objects.get_or_create(name='Matrix FS 2026', defaults={'version': 1})

        # 2. Reference Data (The "Vocabulary")
        codes = [
            # RBRVS & Flat
            ('99213', 'CPT', '100.00', 1.0),   # Standard Office
            ('73030', 'CPT', '50.00', 0.5),    # X-Ray
            # DRG (We use work_rvu as "Relative Weight")
            ('DRG-470', 'DRG', '0.00', 2.5),   # Knee Replacement (Weight 2.5)
            ('DRG-194', 'DRG', '0.00', 0.8),   # Simple Pneumonia (Weight 0.8)
            # Per Diem (Rev Codes)
            ('0120', 'REV_CODE', '0.00', 0.0),      # Room & Board Semi-Private
            # Percent Billed
            ('29806', 'CPT', '0.00', 0.0),     # Implant (Carve out)
            # Stop Loss
            ('SL-TRIG', 'CPT', '0.00', 0.0),   # Trigger Code
            # Dependency
            ('00100', 'CPT', '200.00', 0.0),   # Anesthesia Base
            ('99100', 'CPT', '50.00', 0.0),    # Add-on (Requires 00100)
        ]

        for cid, ctype, rate, rvu in codes:
            RefProcedureCode.objects.update_or_create(
                code_id=cid, code_type=ctype, 
                defaults={'work_rvu': Decimal(rvu)} # Storing DRG Weight here
            )
            FeeScheduleRate.objects.update_or_create(
                fee_schedule=fs, code_id=cid, 
                defaults={'rate_amount': Decimal(rate)}
            )

        # Modifiers
        RefModifier.objects.update_or_create(modifier_code='26', defaults={'percentage_adjustment': 40.00})
        RefModifier.objects.update_or_create(modifier_code='50', defaults={'percentage_adjustment': 150.00})
        RefModifier.objects.update_or_create(modifier_code='XX', defaults={'percentage_adjustment': 0.00}) # For failure test

        # 3. Rules Layering (The Logic)

        # A. RBRVS (Standard)
        PricingRule.objects.get_or_create(
            contract=contract, rule_name='Standard RBRVS',
            defaults={'rule_type': 'BASE', 'methodology_code': 'RBRVS', 'multiplier': 1.5, 'base_fee_schedule': fs, 'specificity_score': 10}
        )

        # B. Flat Rate (X-Ray)
        r_flat, _ = PricingRule.objects.get_or_create(
            contract=contract, rule_name='X-Ray Flat',
            defaults={'rule_type': 'BASE', 'methodology_code': 'FLAT_RATE', 'flat_rate': 75.00, 'specificity_score': 20}
        )
        PricingRuleCondition.objects.get_or_create(pricing_rule=r_flat, attribute_name='code', attribute_value='73030')

        # C. Percent of Billed (Implant)
        r_pct, _ = PricingRule.objects.get_or_create(
            contract=contract, rule_name='Implant 50%',
            defaults={'rule_type': 'BASE', 'methodology_code': 'PERCENT_BILLED', 'multiplier': 0.50, 'specificity_score': 20}
        )
        PricingRuleCondition.objects.get_or_create(pricing_rule=r_pct, attribute_name='code', attribute_value='29806')

        # D. DRG Pricing (Base Rate * Weight)
        # Rule: Any code starting with 'DRG-' uses this rule.
        r_drg, _ = PricingRule.objects.get_or_create(
            contract=contract, rule_name='Inpatient DRG',
            defaults={'rule_type': 'BASE', 'methodology_code': 'DRG', 'flat_rate': 6000.00, 'specificity_score': 30} # $6k Base Rate
        )
        PricingRuleCondition.objects.get_or_create(pricing_rule=r_drg, attribute_name='code', operator='STARTS', attribute_value='DRG-')

        # E. Per Diem
        r_pd, _ = PricingRule.objects.get_or_create(
            contract=contract, rule_name='Per Diem Medical',
            defaults={'rule_type': 'BASE', 'methodology_code': 'PER_DIEM', 'flat_rate': 1200.00, 'specificity_score': 30} # $1200 / Day
        )
        PricingRuleCondition.objects.get_or_create(pricing_rule=r_pd, attribute_name='code', attribute_value='0120')

        # F. Stop Loss (Global)
        PricingRule.objects.get_or_create(
            contract=contract, rule_name='Stop Loss > 10k',
            defaults={'rule_type': 'STOP_LOSS', 'methodology_code': 'PERCENT_BILLED', 'multiplier': 0.60, 'flat_rate': 10000.00, 'specificity_score': 99}
        )

        self.stdout.write("✅ Matrix Data Seeded.")