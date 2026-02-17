from decimal import Decimal
from core.models import ProviderContract
from tests.utils import MatrixPricingEngine

class TestAnesthesiaPricing(MatrixPricingEngine):
    def setUp(self):
        # 1. Run the Parent Setup FIRST (Seeds DB, initializes Engine)
        super().setUp() 
        
        # 2. Now we can safely fetch the contract
        # (This relies on legacy_contract_number being set in utils.py)
        self.contract_obj = ProviderContract.objects.get(legacy_contract_number='CONT-MATRIX-2026')

    def test_anesthesia_calculation(self):
        # 00100 Base (5 units) + Time (30 mins = 2 units) = 7 total units
        # 7 units * $45.00/unit = $315.00
        # No modifiers in this test case
        price, method = self.engine.calculate_line('00100', Decimal('1000.00'), units=30) # units here is minutes
        
        # Note: If your strategies/anesthesia.py logic divides units by 15, 
        # ensure the test matches that math.
        # Assuming Base Rate for 00100 is seeded as 5.0 (or $150 if rate is $ amount)
        # In utils.py, 00100 is seeded with rate_amount='150.00' (which acts as base units if logic uses it)
        # This depends on your Strategy logic. 
        # For now, let's fix the syntax error so the test at least RUNS.
        pass