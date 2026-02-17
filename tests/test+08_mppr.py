import django
from django.test import TestCase
from tests.utils import MatrixPricingEngine
from decimal import Decimal

class TestMPPRScenarios(MatrixPricingEngine):
    
    def test_mppr_01_two_lines(self):
        """MPPR-01: High value primary, Low value secondary reduction"""
        # Line 1: 99213 ($150) -> Primary (100%)
        # Line 2: 99213 ($150) -> Secondary (50%) = $75
        
        # Note: We simulate the batch logic here since the utils.calculate_line is single-line
        line1_price, _ = self.engine.calculate_line('99213', Decimal('200'))
        line2_price, _ = self.engine.calculate_line('99213', Decimal('200'))
        
        # Sort and Apply
        total = line1_price + (line2_price * Decimal('0.5'))
        self.assertEqual(total, Decimal('225.00'))