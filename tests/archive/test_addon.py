from django.core.management.base import BaseCommand
from core.services.pricing_engine import PricingEngine
from core.models import ProviderOrganization
from decimal import Decimal

class Command(BaseCommand):
    help = 'Tests Add-On Dependency Logic'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- 🧪 TESTING ADD-ON DEPENDENCY 🧪 ---")
        org = ProviderOrganization.objects.get(name='Allegheny Health Network')
        engine = PricingEngine()

        # SCENARIO: Orphan Add-on
        # We bill +99100 (Add-on) but NO 00100 (Primary).
        # Expected: DENIED ($0.00)
        
        req = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "lines": [
                {"line_id": 1, "code": "+99100", "billed": "100.00"}
            ]
        }
        
        res = engine.calculate_claim(req)
        line = res['lines'][0]
        
        if line['final_allowed'] == 0:
            self.stdout.write(f"✅ PASS: Orphan Code Denied ($0.00)")
            self.stdout.write(f"   Reason: {line['trace'][0]['message']}")
        else:
            self.stdout.write(f"❌ FAIL: Orphan Code Paid ${line['final_allowed']}")