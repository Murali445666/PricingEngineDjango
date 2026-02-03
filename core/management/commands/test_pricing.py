from django.core.management.base import BaseCommand
from core.services.pricing_engine import PricingEngine
from core.models import ProviderOrganization
import json
from decimal import Decimal

class Command(BaseCommand):
    help = 'Runs diagnostic tests on the Pricing Engine'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- STARTING ENGINE DIAGNOSTIC ---\n")
        
        # 1. Setup Context
        try:
            org = ProviderOrganization.objects.get(name='Allegheny Health Network')
        except ProviderOrganization.DoesNotExist:
            self.stdout.write("❌ Error: Run 'python manage.py seed_data' first.")
            return

        engine = PricingEngine()

        # ---------------------------------------------------------
        # TEST A: Psych Claim (Carve-out / Per Diem)
        # ---------------------------------------------------------
        claim_psych = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "rev_code": "0124",
            "code": "90837",
            "units": "5",
            "billed_amount": "5000.00"
        }
        self._run_test("A: Psych Claim (Rev 0124)", engine, claim_psych)

        # ---------------------------------------------------------
        # TEST B: Office Visit (Standard / RBRVS)
        # ---------------------------------------------------------
        claim_office = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "rev_code": "0510",
            "code": "99213",
            "billed_amount": "150.00"
        }
        self._run_test("B: Office Visit (CPT 99213)", engine, claim_office)

        # ---------------------------------------------------------
        # TEST C: Knee Surgery + Implant (Base + Add-on)
        # ---------------------------------------------------------
        claim_knee = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "rev_code": "0278",
            "code": "27447",
            "billed_amount": "5000.00"
        }
        self._run_test("C: Knee Surgery + Implant (Stacked)", engine, claim_knee)

        # ---------------------------------------------------------
        # TEST D: Bilateral Knee Surgery (Modifier Logic)
        # Expectation: Base ($1875) * 1.50 (Mod 50) = $2812.50
        # ---------------------------------------------------------
        claim_bilateral = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "code": "27447",
            "modifier": "50", # <--- Triggers Adjustment Rule
            "billed_amount": "8000.00"
        }
        self._run_test("D: Bilateral Knee (Modifier 50)", engine, claim_bilateral)

        # ---------------------------------------------------------
        # TEST E: High Cost Implant (Stop Loss Logic)
        # Expectation: 
        #   1. Add-on ($500)
        #   2. Stop Loss: ($20k Billed - $10k Threshold) = $10k Excess
        #   3. Pay 50% of Excess = $5,000
        #   Total: $5,500
        # ---------------------------------------------------------
        claim_stoploss = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "rev_code": "0278",
            "billed_amount": "20000.00" # <--- Triggers Stop Loss
        }
        self._run_test("E: High Cost Implant (Stop Loss)", engine, claim_stoploss)

        # ... (Previous tests) ...

        # ---------------------------------------------------------
        # TEST F: Inpatient Knee Replacement (DRG Logic)
        # Expectation: 
        #   Hospital Base ($10,000) * DRG 470 Weight (2.05)
        #   Total: $20,500.00
        # ---------------------------------------------------------
        claim_drg = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "code": "470", # DRG Code
            "billed_amount": "45000.00"
        }
        self._run_test("F: Inpatient Knee (DRG 470)", engine, claim_drg)

    def _run_test(self, name, engine, claim):
        self.stdout.write(f"\n🔎 TEST {name}")
        result = engine.calculate_price(claim)
        
        # Pretty Print Result
        print(f"   💰 ALLOWED: ${result.get('allowed_amount', 0.0)}")
        print(f"   📜 RULE:    {result.get('rule_id')}")
        print("   🔍 TRACE:")
        
        for log in result.get('trace', []):
            msg = f"      [{log['step']}] {log['message']}"
            if log['step'] == 'ACCUM':
                print(f"\033[92m{msg}\033[0m") # Green
            elif log['step'] == 'SKIP':
                print(f"\033[90m{msg}\033[0m") # Grey
            elif log['step'] == 'ADJUST':
                print(f"\033[96m{msg}\033[0m") # Cyan
            elif log['step'] == 'OUTLIER':
                print(f"\033[93m{msg}\033[0m") # Yellow
            else:
                print(msg)