from django.core.management.base import BaseCommand
from core.services.pricing_engine import PricingEngine
from core.models import ProviderOrganization
from decimal import Decimal

class Command(BaseCommand):
    help = 'Runs 35 Extensive Diagnostic Tests'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- STARTING EXTENSIVE DIAGNOSTIC ---\n")
        
        try:
            org = ProviderOrganization.objects.get(name='Allegheny Health Network')
        except ProviderOrganization.DoesNotExist:
            self.stdout.write("❌ Error: Run 'python manage.py seed_data' first.")
            return

        engine = PricingEngine()
        org_id = str(org.organization_id)
        
        # ------------------------------------------------
        # 1. RBRVS TESTS (Rate * 1.50)
        # ------------------------------------------------
        self.print_header("1. RBRVS METHODOLOGY (Multiplier: 1.50)")
        rbrvs_cases = [
            ("99213", "85.00", "127.50"),
            ("99214", "110.00", "165.00"),
            ("73030", "40.00", "60.00"),
            ("10060", "150.00", "225.00"),
            ("93000", "20.00", "30.00"),
        ]
        for code, rate, expected in rbrvs_cases:
            claim = {"provider_id": org_id, "date_of_service": "2026-06-01", "code": code, "billed_amount": "500.00"}
            self.run_test(engine, f"Code {code}", claim, expected)

        # ------------------------------------------------
        # 2. FLAT RATE TESTS (Fixed $50.00)
        # ------------------------------------------------
        self.print_header("2. FLAT RATE METHODOLOGY ($50.00)")
        flat_cases = ["97110", "97112", "97140", "97530", "98960"]
        for code in flat_cases:
            claim = {"provider_id": org_id, "date_of_service": "2026-06-01", "code": code, "billed_amount": "150.00"}
            self.run_test(engine, f"Therapy {code}", claim, "50.00")

        # ------------------------------------------------
        # 3. DRG HOSPITAL TESTS (Base $10k * Weight)
        # ------------------------------------------------
        self.print_header("3. DRG METHODOLOGY (Base $10k * Weight)")
        drg_cases = [
            ("470", "2.05", "20500.00"),
            ("194", "0.85", "8500.00"),
            ("291", "1.25", "12500.00"),
            ("392", "0.95", "9500.00"),
            ("871", "1.80", "18000.00"),
        ]
        for code, wt, expected in drg_cases:
            claim = {"provider_id": org_id, "date_of_service": "2026-06-01", "code": code, "billed_amount": "50000.00"}
            self.run_test(engine, f"DRG {code} (Wt {wt})", claim, expected)

        # ------------------------------------------------
        # 4. PER DIEM TESTS ($1,250 * Units)
        # ------------------------------------------------
        self.print_header("4. PER DIEM METHODOLOGY ($1,250/day)")
        per_diem_cases = [
            ("0124", 1, "1250.00"),
            ("0114", 2, "2500.00"),
            ("0120", 3, "3750.00"),
            ("0130", 4, "5000.00"),
            ("0140", 5, "6250.00"),
        ]
        for rev, units, expected in per_diem_cases:
            claim = {"provider_id": org_id, "date_of_service": "2026-06-01", "rev_code": rev, "units": units, "billed_amount": "8000.00"}
            self.run_test(engine, f"Rev {rev} ({units} days)", claim, expected)

        # ------------------------------------------------
        # 5. PERCENT OF BILLED (45% of Billed)
        # ------------------------------------------------
        self.print_header("5. PERCENT OF BILLED (45%)")
        pct_cases = [
            ("99999", "1000.00", "450.00"),
            ("T1015", "200.00", "90.00"),
            ("A0999", "500.00", "225.00"),
            ("J3490", "100.00", "45.00"),
            ("E1399", "3000.00", "1350.00"),
        ]
        for code, billed, expected in pct_cases:
            claim = {"provider_id": org_id, "date_of_service": "2026-06-01", "code": code, "billed_amount": billed}
            self.run_test(engine, f"Unlisted {code} (Bill ${billed})", claim, expected)

        # ------------------------------------------------
        # 6. MODIFIER TESTS (Using Code 99213 Base $127.50)
        # ------------------------------------------------
        self.print_header("6. MODIFIERS (Base $127.50 + Adj)")
        # 50 = 1.5x, 80 = 0.2x, 51 = 0.5x
        mod_cases = [
            ("50", "191.25"),  # 127.50 * 1.5
            ("80", "25.50"),   # 127.50 * 0.20
            ("51", "63.75"),   # 127.50 * 0.50
        ]
        for mod, expected in mod_cases:
            claim = {"provider_id": org_id, "date_of_service": "2026-06-01", "code": "99213", "modifier": mod, "billed_amount": "500.00"}
            self.run_test(engine, f"Mod {mod}", claim, expected)

        # ------------------------------------------------
        # 7. STOP LOSS (Threshold $10k, Pay 50% Excess + $500 Base)
        # ------------------------------------------------
        self.print_header("7. STOP LOSS (Threshold $10k)")
        # Base is always $500 for Rev 0278
        sl_cases = [
            ("5000.00", "500.00"),   # Under Threshold ($500 Base + $0)
            ("10000.00", "500.00"),  # At Threshold ($500 Base + $0)
            ("12000.00", "1500.00"), # Excess $2k -> $1k pay + $500 Base = $1500
            ("20000.00", "5500.00"), # Excess $10k -> $5k pay + $500 Base = $5500
            ("100000.00", "45500.00"), # Excess $90k -> $45k pay + $500 Base = $45500
        ]
        for billed, expected in sl_cases:
            claim = {"provider_id": org_id, "date_of_service": "2026-06-01", "rev_code": "0278", "billed_amount": billed}
            self.run_test(engine, f"Implant (Bill ${billed})", claim, expected)

        # ------------------------------------------------
        # 8. OUT OF NETWORK (OON)
        # Expectation: Rate $85.00 * 1.00 (OON) = $85.00
        # (Compare to Test 1 which was $127.50 for INN)
        # ------------------------------------------------
        self.print_header("8. OON PRICING (Multiplier 1.00)")
        claim_oon = {
            "provider_id": org_id,
            "date_of_service": "2026-06-01",
            "code": "99213",
            "billed_amount": "200.00",
            "network_status": "OON" # <--- Trigger
        }
        self.run_test(engine, "OON Office Visit", claim_oon, "85.00")

    def print_header(self, title):
        self.stdout.write(f"\n\033[1;36m{title}\033[0m")
        self.stdout.write("=" * 60)

    def run_test(self, engine, name, claim, expected_str):
        result = engine.calculate_price(claim)
        actual = result.get('allowed_amount', Decimal('0.00'))
        expected = Decimal(expected_str)
        
        # Tolerance for rounding
        if abs(actual - expected) < Decimal('0.01'):
            status = "✅ PASS"
            color = "\033[92m" # Green
        else:
            status = f"❌ FAIL (Exp: {expected}, Got: {actual})"
            color = "\033[91m" # Red
            
        print(f"{color}{status:<30} {name:<40} ${actual}\033[0m")