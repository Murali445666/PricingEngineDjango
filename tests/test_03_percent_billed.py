import django
from django.test import TestCase
from tests.utils import MatrixPricingEngine
from decimal import Decimal

class TestPercentBilledPricing(MatrixPricingEngine):
   
    def test_pct_01_standard(self):
        """PCT-01: Percent of billed standard"""
        # Billed $1,000 * 0.50 = $500.00
        price, method = self.engine.calculate_line('29806', Decimal('1000.00'))
        self.assertEqual(price, Decimal('500.00'))
        self.assertEqual(method, 'PERCENT_BILLED')

    def test_pct_02_high_dollar(self):
        """PCT-02: Percent billed with high billed amount (Pre-Stop Loss)"""
        # Billed $5,000 * 0.50 = $2,500.00 (Below $10k Stop Loss)
        price, _ = self.engine.calculate_line('29806', Decimal('5000.00'))
        self.assertEqual(price, Decimal('2500.00'))