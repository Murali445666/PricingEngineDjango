from django.test import TestCase
from decimal import Decimal
from tests.utils import MatrixPricingEngine

class TestFailureModes(MatrixPricingEngine):
    
    def test_err_01_missing_rule(self):
        """ERR-01: Code with no Fee Schedule rate should return Error"""
        price, method = self.engine.calculate_line('99999', Decimal("100.00"))
        
        # New Architecture returns 0.00 price and a Status Code
        self.assertEqual(price, Decimal("0.00"))
        
        # FIX: Expect the standardized Enum name, not the old string
        self.assertEqual(method, 'DENIED_CALCULATION_ERROR')