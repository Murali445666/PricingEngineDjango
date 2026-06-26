"""Tests for APC (OPPS) pricing strategy."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import (
    ProviderContract,
    ProviderOrganization,
    PayerNetwork,
    FeeSchedule,
    PricingRule,
    PricingRuleCondition,
    RefApc,
)
from core.engine.orchestrator import PricingEngine
from core.engine.types import PricingInput, PricingStatus


class TestAPCPricing(TestCase):
    """APC strategy: allowed = relative_weight * conversion_factor * units. NO_APC_FOUND when missing."""

    def setUp(self):
        self.engine = PricingEngine()
        payer_org = ProviderOrganization.objects.create(
            organization_id="PAYER-APC", name="Payer", tax_id="00-0000000"
        )
        provider_org = ProviderOrganization.objects.create(
            organization_id="PROV-APC", name="Provider", tax_id="11-1111111"
        )
        network = PayerNetwork.objects.create(
            network_id="NET-APC", network_name="APC Network", payer_org=payer_org
        )
        self.contract = ProviderContract.objects.create(
            contract_name="APC Contract",
            legacy_contract_number="CONT-APC",
            status="ACTIVE",
            effective_start_date="2025-01-01",
            provider_org=provider_org,
            network=network,
        )
        # RefApc: apc_code 5121, year 2025, relative_weight 1.5
        RefApc.objects.create(
            apc_code="5121",
            description="Level 1 Clinic",
            relative_weight=Decimal("1.50"),
            status_indicator="J",
            payment_rate=Decimal("100.00"),
            year=2025,
        )
        rule = PricingRule.objects.create(
            contract=self.contract,
            rule_name="OPPS APC",
            specificity_score=10,
            methodology_code="APC",
            multiplier=Decimal("100.00"),  # conversion_factor
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="5121",
        )

    def test_apc_01_allowed_amount(self):
        """APC: relative_weight * conversion_factor * units."""
        inp = PricingInput(
            procedure_code="5121",
            billed_amount=Decimal("200.00"),
            units=1,
            service_date=date(2025, 6, 15),
        )
        result = self.engine.calculate_line(self.contract, inp)
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.allowed_amount, Decimal("150.00"))  # 1.5 * 100 * 1

    def test_apc_02_units(self):
        """APC: multiple units."""
        inp = PricingInput(
            procedure_code="5121",
            billed_amount=Decimal("200.00"),
            units=3,
            service_date=date(2025, 6, 15),
        )
        result = self.engine.calculate_line(self.contract, inp)
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.allowed_amount, Decimal("450.00"))  # 1.5 * 100 * 3

    def test_apc_03_no_apc_found(self):
        """APC: unknown procedure code returns NO_APC_FOUND and zero amount."""
        rule = PricingRule.objects.create(
            contract=self.contract,
            rule_name="APC Other",
            specificity_score=5,
            methodology_code="APC",
            multiplier=Decimal("100.00"),
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="9999",
        )
        inp = PricingInput(
            procedure_code="9999",
            billed_amount=Decimal("100.00"),
            units=1,
            service_date=date(2025, 6, 15),
        )
        result = self.engine.calculate_line(self.contract, inp)
        self.assertEqual(result.status, PricingStatus.NO_APC_FOUND)
        self.assertEqual(result.allowed_amount, Decimal("0.00"))
        self.assertIn("NO_APC_FOUND", result.details)
