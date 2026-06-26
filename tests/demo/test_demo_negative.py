"""Negative / no-match scenario on seeded DEMO_RBRVS."""
from django.test import TestCase

from core.demo.deterministic_seed import seed_deterministic_demos
from core.demo.scenarios import NEGATIVE_SCENARIO
from tests.demo.helpers import simulate_claim, status_value


class DemoNegativePricingTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.registry = seed_deterministic_demos()

    def test_denied_no_rule(self):
        scenario = NEGATIVE_SCENARIO
        result = simulate_claim(self.registry, scenario["contract_key"], scenario["claim"])
        exp = scenario["expected"]
        line = result.lines[0]
        self.assertEqual(status_value(line.status), exp["line_status"])
        self.assertEqual(line.allowed_amount, exp["line_allowed"])
        self.assertEqual(line.rule_id or 0, exp["rule_id"])
