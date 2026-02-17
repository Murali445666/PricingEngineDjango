from django.core.management.base import BaseCommand
from core.services.pricing_engine import PricingEngine
from core.models import ProviderOrganization
from decimal import Decimal

class Command(BaseCommand):
    help = 'Runs extensive diagnostic tests on the Pricing Engine (Adapted for Multi-Line Engine)'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- STARTING EXTENSIVE DIAGNOSTIC ---")
        
        # 1. SETUP
        try:
            org = ProviderOrganization.objects.get(name='Allegheny Health Network')
            org_id = str(org.organization_id)
        except ProviderOrganization.DoesNotExist:
            self.stdout.write("❌ ERROR: Run 'python manage.py seed_data' first.")
            return

        engine = PricingEngine()

        # ------------------------------------------------
        # 1. RBRVS (Multiplier 1.50)
        # ------------------------------------------------
        self.print_header("1. RBRVS METHODOLOGY (Multiplier: 1.50)")
        
        # Test 1: 99213 ($85.00 * 1.50 = 127.50)
        self.run_test(engine, org_id, "Code 99213", "99213", "127.50")
        
        # Test 2: 99214 ($110.00 * 1.50 = 165.00)
        self.run_test(engine, org_id, "Code 99214", "99214", "165.00")
        
        # Test 3: 73030 ($40.00 * 1.50 = 60.00)
        self.run_test(engine, org_id, "Code 73030", "73030", "60.00")

        # ------------------------------------------------
        # 2. FLAT RATE ($50.00)
        # ------------------------------------------------
        self.print_header("2. FLAT RATE METHODOLOGY ($50.00)")
        self.run_test(engine, org_id, "Therapy 97110", "97110", "50.00")
        self.run_test(engine, org_id, "Therapy 97140", "97140", "50.00")

        # ------------------------------------------------
        # 3. DRG ($10k Base * Weight)
        # ------------------------------------------------
        self.print_header("3. DRG METHODOLOGY (Base $10k * Weight)")
        # 470 Weight 2.05 -> $20,500
        self.run_test(engine, org_id, "DRG 470 (Wt 2.05)", "470", "20500.00")
        # 194 Weight 0.85 -> $8,500
        self.run_test(engine, org_id, "DRG 194 (Wt 0.85)", "194", "8500.00")

        # ------------------------------------------------
        # 4. PER DIEM ($1,250/day)
        # ------------------------------------------------
        self.print_header("4. PER DIEM METHODOLOGY ($1,250/day)")
        # Rev 0124 * 1 Unit
        self.run_test(engine, org_id, "Rev 0124 (1 day)", None, "1250.00", rev_code="0124", units=1)
        # Rev 0124 * 3 Units
        self.run_test(engine, org_id, "Rev 0124 (3 days)", None, "3750.00", rev_code="0124", units=3)

        # ------------------------------------------------
        # 5. PERCENT OF BILLED (45%)
        # ------------------------------------------------
        self.print_header("5. PERCENT OF BILLED (45%)")
        # $1000 billed * 0.45 = $450
        self.run_test(engine, org_id, "Unlisted 99999", "99999", "450.00", billed="1000.00")

        # ------------------------------------------------
        # 6. MODIFIERS (Adjustments)
        # ------------------------------------------------
        self.print_header("6. MODIFIERS (Base $127.50 + Adj)")
        # Mod 50 (1.5x) -> $127.50 * 1.5 = $191.25
        self.run_test(engine, org_id, "Mod 50 (Bilateral)", "99213", "191.25", modifier="50")
        
        # Mod 80 (0.2x) -> $127.50 * 0.2 = $25.50
        self.run_test(engine, org_id, "Mod 80 (Assistant)", "99213", "25.50", modifier="80")

        # ------------------------------------------------
        # 7. STOP LOSS (Threshold $10k)
        # ------------------------------------------------
        self.print_header("7. STOP LOSS (Implants)")
        # Base Implant Pay ($500) + 50% of (Billed - 10k)
        # Billed $5,000 (Under threshold) -> Just Base $500
        self.run_test(engine, org_id, "Implant < Threshold", None, "500.00", rev_code="0278", billed="5000.00")
        
        # Billed $12,000 (Over threshold) -> Excess $2,000 -> Pay $1,000 + Base $500 = $1500
        self.run_test(engine, org_id, "Implant > Threshold", None, "1500.00", rev_code="0278", billed="12000.00")

        # ------------------------------------------------
        # 8. OUT OF NETWORK
        # ------------------------------------------------
        self.print_header("8. OON PRICING")
        # Should hit Rule 8 (Multiplier 1.0) instead of Rule 1 (1.5)
        # 99213 ($85) * 1.0 = $85.00
        self.run_test(engine, org_id, "OON Office Visit", "99213", "85.00", network_status="OON")


    # --- HELPER METHODS ---

    def print_header(self, title):
        self.stdout.write(f"\n{title}")
        self.stdout.write("="*60)

    def run_test(self, engine, org_id, name, code, expected_str, modifier=None, rev_code=None, units=1, billed="100.00", network_status="INN"):
        # 1. CONSTRUCT THE NEW "CLAIM" REQUEST STRUCTURE
        claim_request = {
            "provider_id": org_id,
            "date_of_service": "2026-06-01",
            "network_status": network_status,
            "lines": [
                {
                    "line_id": 1,
                    "code": code,
                    "rev_code": rev_code,
                    "modifier": modifier,
                    "units": units,
                    "billed_amount": billed
                }
            ]
        }

        # 2. RUN ENGINE
        result = engine.calculate_claim(claim_request)
        
        # 3. EXTRACT LINE 1 RESULT
        line_result = result['lines'][0]
        actual_val = line_result['final_allowed']
        expected_val = Decimal(expected_str)

        # 4. COMPARE
        if actual_val == expected_val:
            self.stdout.write(f"✅ PASS {name:<30} ${actual_val:.4f}")
        else:
            self.stdout.write(f"❌ FAIL {name:<30} Exp: {expected_val} | Got: {actual_val}")