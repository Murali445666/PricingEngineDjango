from django.core.management.base import BaseCommand
from core.services.pricing_engine import PricingEngine
from core.models import ProviderOrganization
import json

class Command(BaseCommand):
    help = 'Debugs a single claim to see why it pays $0.00'

    def handle(self, *args, **kwargs):
        self.stdout.write("--- STARTING DEBUG CLAIM ---")
        
        # 1. Get Organization
        try:
            org = ProviderOrganization.objects.get(name='Allegheny Health Network')
            self.stdout.write(f"✅ Found Org: {org} (ID: {org.organization_id})")
        except ProviderOrganization.DoesNotExist:
            self.stdout.write("❌ ERROR: Organization 'Allegheny Health Network' not found.")
            return

        # 2. Define the Test Claim (RBRVS 99213)
        claim = {
            "provider_id": str(org.organization_id),
            "date_of_service": "2026-06-01",
            "code": "99213",
            "billed_amount": "500.00"
        }
        self.stdout.write(f"🔎 Processing Claim: Code {claim['code']} for DOS {claim['date_of_service']}")

        # 3. Run Engine
        engine = PricingEngine()
        result = engine.calculate_price(claim)

        # 4. PRINT THE TRACE LOGS (The Important Part)
        self.stdout.write("\n🔎 TRACE LOGS:")
        trace = result.get('trace', [])
        
        if not trace:
            self.stdout.write("❌ NO TRACE LOGS GENERATED. (Did the engine crash silently?)")
        
        for step in trace:
            msg = f"[{step['step']}] {step['message']}"
            if step['step'] == 'SKIP':
                print(f"   ❌ {msg}")
            elif step['step'] in ['ACCUM', 'CALC', 'SUCCESS']:
                print(f"   ✅ {msg}")
            elif step['step'] in ['STOP', 'ERROR']:
                print(f"   🛑 {msg}")
            else:
                print(f"   ℹ️ {msg}")

        self.stdout.write(f"\n💰 FINAL PRICE: ${result.get('allowed_amount', 0)}")