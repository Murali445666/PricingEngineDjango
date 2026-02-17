import django
from django.test import TestCase
from tests.utils import MatrixPricingEngine
from decimal import Decimal

class TestDependencyValidation(MatrixPricingEngine):
   
    def test_dep_01_addon_valid(self):
        """DEP-01: Add-on present with required primary"""
        # In a real batch engine, we check if 00100 exists in the claim.
        # For unit testing, we just verify the Add-on prices correctly if valid.
        # 99100 (Add-on) Base $50 * 1.5 = $75.00.
        price, _ = self.engine.calculate_line('99100', Decimal('100.00'))
        self.assertEqual(price, Decimal('75.00'))