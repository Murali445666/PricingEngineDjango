import os
import sys
import django

# 1. Add the current folder to Python's path
# This fixes "ModuleNotFoundError: No module named 'PricingEngineDjango'"
sys.path.append(os.getcwd())

# 2. Setup Django Context
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PricingEngineDjango.settings')
django.setup()

# 3. Imports (Must happen AFTER setup)
from core.services.pricing_engine import PricingEngine
from core.models import ProviderOrganization
from decimal import Decimal

def run_debug():
    print("--- STARTING SINGLE CLAIM DEBUG ---")
    
    # 1. Get Org
    try:
        org = ProviderOrganization.objects.get(name='Allegheny Health Network')
    except ProviderOrganization.DoesNotExist:
        print("❌ CRITICAL ERROR: Organization 'Allegheny Health Network' not found.")
        print("   -> Run 'python manage.py seed_data' first.")
        return

    # 2. Setup Engine & Claim
    engine = PricingEngine()
    claim = {
        "provider_id": str(org.organization_id),
        "date_of_service": "2026-06-01",
        "code": "99213",
        "billed_amount": "500.00"
    }

    print(f"🔎 Testing Claim: Provider={claim['provider_id']} | Code={claim['code']}")

    # 3. Execute
    result = engine.calculate_price(claim)

    # 4. Print Trace
    print("\n🔍 TRACE LOGS:")
    for step in result.get('trace', []):
        msg = f"[{step['step']}] {step['message']}"
        if step['step'] == 'SKIP':
            print(f"   ❌ {msg}")
        elif step['step'] in ['ACCUM', 'CALC', 'SUCCESS']:
            print(f"   ✅ {msg}")
        elif step['step'] in ['STOP', 'ERROR']:
            print(f"   🛑 {msg}")
        else:
            print(f"   ℹ️ {msg}")

    print(f"\n💰 FINAL PRICE: ${result.get('allowed_amount', 0)}")

if __name__ == "__main__":
    run_debug()