import django
from django.test import TestCase
from tests.utils import MatrixPricingEngine
from decimal import Decimal

class TestFlatRatePricing(MatrixPricingEngine):
   
    def test_flat_01_standard(self):
        """FLAT-01: Simple flat rate pricing"""
        # Rule: X-Ray Flat ($75.00). Ignores the FS rate of $50.
        price, method = self.engine.calculate_line('73030', Decimal('200.00'))
        self.assertEqual(price, Decimal('75.00'))
        self.assertEqual(method, 'FLAT_RATE')

    def test_flat_02_units(self):
        """FLAT-02: Flat rate × units"""
        # $75.00 * 2 Units = $150.00
        price, _ = self.engine.calculate_line('73030', Decimal('400.00'), units=2)
        self.assertEqual(price, Decimal('150.00'))