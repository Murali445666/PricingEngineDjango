from django.core.management.base import BaseCommand
from core.services.pricing_engine import PricingEngine
from core.models import ProviderOrganization
from decimal import Decimal
import json

class Command(BaseCommand):
    help = 'Tests MPPR Logic (Multi-Line Pricing)'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- 🏥 STARTING MPPR TEST 🏥 ---")
        
        # 1. Setup Data
        try:
            org = ProviderOrganization.objects.get(name='Allegheny Health Network')
        except:
            self.stdout.write("❌ Run seed_data first.")
            return

        # 2. Construct Multi-Line Claim
        # Line 1: 99214 (Allowed $165.00) -> Highest
        # Line 2: 99213 (Allowed $127.50) -> Lower (Should get MPPR'd)
        claim_request = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "network_status": "INN",
            "lines": [
                {"line_id": 1, "code": "99214", "billed": "200.00"},
                {"line_id": 2, "code": "99213", "billed": "150.00"}
            ]
        }

        # 3. Run Engine
        engine = PricingEngine()
        result = engine.calculate_claim(claim_request)

        # 4. Analyze Results
        self.stdout.write(f"\n📋 Claim Total: ${result['claim_total']}")
        
        # Validation
        # Line 1 (99214): Expected $165.00 (100%)
        # Line 2 (99213): Expected $63.75  (50% of $127.50)
        # Total: $228.75
        
        expected_total = Decimal('228.75')
        
        for line in result['lines']:
            lid = line['line_id']
            gross = line['gross_allowed']
            final = line['final_allowed']
            note = ""
            if gross != final:
                note = "🔻 MPPR APPLIED"
            
            self.stdout.write(f"   Line {lid} ({line['code']}): Gross ${gross} -> Final ${final} {note}")

        if result['claim_total'] == expected_total:
            self.stdout.write("\n✅ PASS: MPPR Logic verified correctly.")
        else:
            self.stdout.write(f"\n❌ FAIL: Expected ${expected_total}, Got ${result['claim_total']}")