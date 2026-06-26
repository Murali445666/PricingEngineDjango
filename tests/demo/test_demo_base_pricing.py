"""Deterministic DEMO_* base payment-type scenarios."""
from decimal import Decimal

from django.test import TestCase

from core.demo.deterministic_seed import seed_deterministic_demos
from core.demo.scenarios import BASE_SCENARIOS
from tests.demo.helpers import simulate_claim, status_value


class DemoBasePricingTests(TestCase):
    """One test per primary payment methodology contract."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.registry = seed_deterministic_demos()

    def _run(self, contract_key: str):
        scenario = BASE_SCENARIOS[contract_key]
        return simulate_claim(self.registry, contract_key, scenario["claim"])

    def test_demo_rbrvs(self):
        result = self._run("DEMO_RBRVS")
        exp = BASE_SCENARIOS["DEMO_RBRVS"]["expected"]
        self.assertEqual(len(result.lines), 1)
        line = result.lines[0]
        self.assertEqual(status_value(line.status), exp["line_status"])
        self.assertEqual(line.methodology, exp["methodology"])
        self.assertEqual(line.allowed_amount, exp["line_allowed"])
        self.assertEqual(result.total_allowed, exp["total_allowed"])

    def test_demo_drg_claim_level(self):
        result = self._run("DEMO_DRG")
        exp = BASE_SCENARIOS["DEMO_DRG"]["expected"]
        self.assertEqual(result.total_allowed, exp["total_allowed"])
        trace_text = " ".join(result.claim_trace or [])
        self.assertIn(exp["claim_trace_contains"], trace_text)

    def test_demo_flat(self):
        result = self._run("DEMO_FLAT")
        exp = BASE_SCENARIOS["DEMO_FLAT"]["expected"]
        line = result.lines[0]
        self.assertEqual(status_value(line.status), exp["line_status"])
        self.assertEqual(line.methodology, exp["methodology"])
        self.assertEqual(line.allowed_amount, exp["line_allowed"])
        self.assertEqual(result.total_allowed, exp["total_allowed"])

    def test_demo_pct_billed(self):
        result = self._run("DEMO_PCT_BILLED")
        exp = BASE_SCENARIOS["DEMO_PCT_BILLED"]["expected"]
        line = result.lines[0]
        self.assertEqual(line.methodology, exp["methodology"])
        self.assertEqual(line.allowed_amount, exp["line_allowed"])
        self.assertEqual(result.total_allowed, exp["total_allowed"])

    def test_demo_apc(self):
        result = self._run("DEMO_APC")
        exp = BASE_SCENARIOS["DEMO_APC"]["expected"]
        line = result.lines[0]
        self.assertEqual(line.methodology, exp["methodology"])
        self.assertEqual(line.allowed_amount, exp["line_allowed"])
        self.assertEqual(result.total_allowed, exp["total_allowed"])

    def test_demo_asp(self):
        result = self._run("DEMO_ASP")
        exp = BASE_SCENARIOS["DEMO_ASP"]["expected"]
        line = result.lines[0]
        self.assertEqual(line.methodology, exp["methodology"])
        self.assertEqual(line.allowed_amount, exp["line_allowed"])
        self.assertEqual(result.total_allowed, exp["total_allowed"])

    def test_demo_per_diem(self):
        result = self._run("DEMO_PER_DIEM")
        exp = BASE_SCENARIOS["DEMO_PER_DIEM"]["expected"]
        line = result.lines[0]
        self.assertEqual(line.methodology, exp["methodology"])
        self.assertEqual(line.allowed_amount, exp["line_allowed"])
        self.assertEqual(result.total_allowed, exp["total_allowed"])

    def test_demo_anesthesia(self):
        result = self._run("DEMO_ANESTHESIA")
        exp = BASE_SCENARIOS["DEMO_ANESTHESIA"]["expected"]
        line = result.lines[0]
        self.assertEqual(line.methodology, exp["methodology"])
        self.assertEqual(line.allowed_amount, exp["line_allowed"])
        self.assertEqual(result.total_allowed, exp["total_allowed"])
