from django.core.management.base import BaseCommand
from core.models import *
from core.services.pricing_engine import PricingEngine
from datetime import date
from decimal import Decimal

class Command(BaseCommand):
    help = 'WIPES database, RE-SEEDS clean data, and RUNS a test.'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- ☢️ STARTING NUCLEAR REBUILD ☢️ ---")

        # 1. WIPE EVERYTHING (The "Clean Slate")
        self.stdout.write("🧹 Deleting ALL old data...")
        PricingRuleCondition.objects.all().delete()
        PricingRule.objects.all().delete()
        FeeScheduleRate.objects.all().delete()
        FeeSchedule.objects.all().delete()
        ProviderContract.objects.all().delete()
        ProviderOrganization.objects.all().delete()
        self.stdout.write("✅ Database Wiped Clean.")

        # 2. SEED FRESH DATA
        self.stdout.write("🌱 Seeding Fresh Data...")
        
        # Setup Core
        cpt_set, _ = CodeSet.objects.get_or_create(code_set_name='CPT')
        fs = FeeSchedule.objects.create(name='Master 2026', effective_start_date=date(2026, 1, 1), version=1)

        # Setup RBRVS Code 99213 (The one that was failing)
        c_99213, _ = Code.objects.get_or_create(code_set=cpt_set, code='99213', defaults={'description': 'Office Visit'})
        FeeScheduleRate.objects.create(fee_schedule=fs, code=c_99213, rate_amount=Decimal('85.00'))

        # Setup Contract
        org = ProviderOrganization.objects.create(name='Allegheny Health Network', tax_id='25-0000000', network_code='HIGHMARK')
        contract = ProviderContract.objects.create(contract_name='AHN Enterprise 2026', provider_org=org, status='ACTIVE', effective_start_date=date(2026, 1, 1))

        # Setup Rule (RBRVS 1.50x)
        method = PricingMethodology.objects.get(methodology_code='RBRVS')
        rule = PricingRule.objects.create(
            contract=contract, rule_type='BASE', methodology=method,
            base_fee_schedule=fs, multiplier=Decimal('1.50'),
            status='ACTIVE', effective_start_date=date(2026, 1, 1)
        )
        PricingRuleCondition.objects.create(pricing_rule=rule, attribute_name='code', operator='EQ', attribute_value='99213')
        rule.calculate_score()
        self.stdout.write("✅ Seeding Complete.")

        # 3. RUN IMMEDIATE TEST
        self.stdout.write("🔎 Running Diagnostic Test (Code 99213)...")
        engine = PricingEngine()
        claim = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "code": "99213",
            "billed_amount": "500.00"
        }
        
        result = engine.calculate_price(claim)
        
        self.stdout.write("\n--- TRACE LOGS ---")
        for step in result.get('trace', []):
            icon = "✅" if step['step'] in ['ACCUM', 'SUCCESS'] else "ℹ️"
            if step['step'] == 'STOP': icon = "🛑"
            self.stdout.write(f"{icon} [{step['step']}] {step['message']}")

        self.stdout.write(f"\n💰 FINAL PRICE: ${result.get('allowed_amount', 0)}")
        
        expected = Decimal('127.50') # 85.00 * 1.50
        if result.get('allowed_amount') == expected:
            self.stdout.write("\n🎉 SUCCESS! The Engine is Fixed.")
        else:
            self.stdout.write(f"\n❌ FAIL. Expected {expected}, Got {result.get('allowed_amount')}")