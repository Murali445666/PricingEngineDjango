import django
from django.test import TestCase
from tests.utils import MatrixPricingEngine
from decimal import Decimal

class TestStopLossScenarios(MatrixPricingEngine):
   
    def test_sl_01_trigger(self):
        """SL-01: Stop loss triggered above threshold"""
        # Billed $15,000 (Above $10k). Rule is 60%.
        # $15,000 * 0.60 = $9,000.00
        # This overrides any specific code rules.
        price, method = self.engine.calculate_line('SL-TRIG', Decimal('15000.00'))
        self.assertEqual(price, Decimal('9000.00'))
        self.assertEqual(method, 'PERCENT_BILLED')

    def test_sl_02_under_threshold(self):
        """SL-02: Stop loss NOT triggered"""
        # Billed $5,000 (Below $10k). Falls back to standard rules.
        # SL-TRIG has no base rule -> Denied ($0) or generic fallback if defined.
        # In our matrix seed, we didn't define a base rule for SL-TRIG, so it denies.
        price, method = self.engine.calculate_line('SL-TRIG', Decimal('5000.00'))
        self.assertEqual(price, Decimal('0.00'))
        self.assertNotEqual(method, 'STOP_LOSS')