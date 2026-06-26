"""Deterministic DEMO_POLICY non-base behavior scenarios (one policy per test)."""
from decimal import Decimal

from django.test import TestCase

from core.demo.deterministic_seed import seed_deterministic_demos
from core.demo.scenarios import POLICY_SCENARIOS
from core.models import ProviderContract
from tests.demo.helpers import simulate_claim, status_value
from tests.demo.policy_fixtures import (
    attach_blending_add,
    attach_carveout_exclude,
    attach_claim_cap,
    attach_claim_floor,
    attach_mppr,
    attach_outlier,
    attach_stop_loss,
    clear_policy_rows,
)


class DemoPolicyPricingTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.registry = seed_deterministic_demos()

    def _policy_version(self):
        contract = ProviderContract.objects.get(pk=self.registry["DEMO_POLICY"]["contract_id"])
        version = contract.versions.get(version_id=self.registry["DEMO_POLICY"]["version_id"])
        clear_policy_rows(version)
        return contract, version

    def test_carveout_exclude(self):
        contract, version = self._policy_version()
        attach_carveout_exclude(version)
        scenario = POLICY_SCENARIOS["carveout_exclude"]
        result = simulate_claim(self.registry, "DEMO_POLICY", scenario["claim"])
        exp = scenario["expected"]
        line = result.lines[0]
        self.assertEqual(status_value(line.status), exp["line_status"])
        self.assertEqual(line.allowed_amount, exp["line_allowed"])
        self.assertEqual(line.base_allowed_amount, exp["base_allowed_before_policy"])
        self.assertEqual(result.total_allowed, exp["total_allowed"])

    def test_stop_loss(self):
        contract, version = self._policy_version()
        attach_stop_loss(contract, version)
        scenario = POLICY_SCENARIOS["stop_loss"]
        result = simulate_claim(self.registry, "DEMO_POLICY", scenario["claim"])
        exp = scenario["expected"]
        self.assertEqual(status_value(result.status), exp["claim_status"])
        self.assertEqual(result.total_allowed, exp["total_allowed"])

    def test_outlier(self):
        contract, version = self._policy_version()
        attach_outlier(contract, version)
        scenario = POLICY_SCENARIOS["outlier"]
        result = simulate_claim(self.registry, "DEMO_POLICY", scenario["claim"])
        exp = scenario["expected"]
        self.assertEqual(status_value(result.status), exp["claim_status"])
        self.assertEqual(result.total_allowed, exp["total_allowed"])

    def test_blending_add(self):
        contract, version = self._policy_version()
        attach_blending_add(version)
        scenario = POLICY_SCENARIOS["blending_add"]
        result = simulate_claim(self.registry, "DEMO_POLICY", scenario["claim"])
        exp = scenario["expected"]
        self.assertEqual(result.total_allowed, exp["total_allowed"])

    def test_claim_cap(self):
        contract, version = self._policy_version()
        attach_claim_cap(version)
        scenario = POLICY_SCENARIOS["claim_cap"]
        result = simulate_claim(self.registry, "DEMO_POLICY", scenario["claim"])
        exp = scenario["expected"]
        self.assertEqual(result.total_allowed, exp["total_allowed"])

    def test_claim_floor(self):
        contract, version = self._policy_version()
        attach_claim_floor(version)
        scenario = POLICY_SCENARIOS["claim_floor"]
        result = simulate_claim(self.registry, "DEMO_POLICY", scenario["claim"])
        exp = scenario["expected"]
        self.assertEqual(result.total_allowed, exp["total_allowed"])

    def test_mppr_two_lines(self):
        contract, version = self._policy_version()
        attach_mppr(contract, version)
        scenario = POLICY_SCENARIOS["mppr"]
        result = simulate_claim(self.registry, "DEMO_POLICY", scenario["claim"])
        exp = scenario["expected"]
        self.assertEqual(len(result.lines), 2)
        self.assertEqual(result.lines[0].allowed_amount, exp["line1_allowed"])
        self.assertEqual(result.lines[1].allowed_amount, exp["line2_allowed_after_mppr"])
        self.assertEqual(result.total_allowed, exp["total_after_mppr_before_blend"])
