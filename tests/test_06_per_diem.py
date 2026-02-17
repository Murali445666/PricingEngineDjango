from django.test import TestCase
from decimal import Decimal
from tests.utils import MatrixPricingEngine

class TestPerDiemPricing(MatrixPricingEngine):
   
    def test_pd_01_los(self):
        """PD-01: Per Diem Rate * Length of Stay (Units)"""
        # Billed $500 (Safe from Stop Loss)
        # Code 0120 ($1200/day) * 5 Days = $6,000
        price, method = self.engine.calculate_line('0120', Decimal('500.00'), units=5)
        self.assertEqual(price, Decimal('6000.00'))
        self.assertEqual(method, 'PER_DIEM')