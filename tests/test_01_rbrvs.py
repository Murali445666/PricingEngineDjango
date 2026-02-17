from decimal import Decimal
from tests.utils import MatrixPricingEngine # <--- MUST IMPORT THIS

class TestRBRVSPricing(MatrixPricingEngine): # <--- MUST INHERIT THIS
    # DELETE def setUp(self): entirely!
    
    def test_rbrvs_01_standard(self):
        price, method = self.engine.calculate_line('99213', Decimal('200.00'))
        self.assertEqual(price, Decimal('150.00'))
        self.assertEqual(method, 'RBRVS')

    def test_rbrvs_03_units(self):
        price, method = self.engine.calculate_line('99213', Decimal('600.00'), units=3)
        self.assertEqual(price, Decimal('450.00'))