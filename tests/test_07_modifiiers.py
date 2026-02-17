import django
from django.test import TestCase
from tests.utils import MatrixPricingEngine
from decimal import Decimal

class TestModifierStacking(MatrixPricingEngine):
   
    def test_mod_01_single(self):
        """MOD-01: Single modifier adjustment (-26)"""
        # 99213 Base: $100 * 1.5 = $150.
        # Mod 26 (40%): $150 * 0.40 = $60.00
        price, _ = self.engine.calculate_line('99213', Decimal('200.00'), modifiers=['26'])
        self.assertEqual(price, Decimal('60.00'))

    def test_mod_02_bilateral(self):
        """MOD-02: Bilateral modifier (50)"""
        # 99213 Base: $150.
        # Mod 50 (150%): $150 * 1.5 = $225.00
        price, _ = self.engine.calculate_line('99213', Decimal('200.00'), modifiers=['50'])
        self.assertEqual(price, Decimal('225.00'))

    def test_mod_03_stacking(self):
        """MOD-03: Multiple modifiers stacked (-26 and -50)"""
        # Base $150 * 0.40 (26) * 1.5 (50)
        # $150 * 0.6 = $90.00? No: 150 * 0.4 = 60. 60 * 1.5 = 90.
        price, _ = self.engine.calculate_line('99213', Decimal('200.00'), modifiers=['26', '50'])
        self.assertEqual(price, Decimal('90.00'))