from django.test import TestCase
from decimal import Decimal
from tests.utils import MatrixPricingEngine

class TestDRGPricing(MatrixPricingEngine):
    
    def test_drg_01_base_weight(self):
        """DRG-01: DRG Base Rate * Weight"""
        # Billed $500.00 (Safe from Stop Loss). 
        # Code DRG-470 (Weight 2.5) * Contract Base ($6,000) = $15,000
        price, method = self.engine.calculate_line('DRG-470', Decimal('500.00')) 
        self.assertEqual(price, Decimal('15000.00'))
        self.assertEqual(method, 'DRG')

    def test_drg_02_low_weight(self):
        """DRG-02: Low weight DRG calculation"""
        # Billed $500.00 (Safe from Stop Loss).
        # Code DRG-194 (Weight 0.8) * Contract Base ($6,000) = $4,800
        price, _ = self.engine.calculate_line('DRG-194', Decimal('500.00'))
        self.assertEqual(price, Decimal('4800.00'))