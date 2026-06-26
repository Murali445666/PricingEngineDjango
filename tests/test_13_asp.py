"""Tests for ASP/Drug pricing strategy."""
from datetime import date
from decimal import Decimal

from django.test import TestCase

from core.models import (
    ProviderContract,
    ProviderOrganization,
    PayerNetwork,
    FeeSchedule,
    FeeScheduleRate,
    PricingRule,
    PricingRuleCondition,
    RefAspPricing,
)
from core.engine.orchestrator import PricingEngine
from core.engine.types import PricingInput, PricingStatus


class TestASPPricing(TestCase):
    """ASP strategy: allowed = payment_limit * units (or asp); fallback to base_rate; NO_ASP_FOUND when missing."""

    def setUp(self):
        self.engine = PricingEngine()
        payer_org = ProviderOrganization.objects.create(
            organization_id="PAYER-ASP", name="Payer", tax_id="00-0000000"
        )
        provider_org = ProviderOrganization.objects.create(
            organization_id="PROV-ASP", name="Provider", tax_id="11-1111111"
        )
        network = PayerNetwork.objects.create(
            network_id="NET-ASP", network_name="ASP Network", payer_org=payer_org
        )
        self.contract = ProviderContract.objects.create(
            contract_name="ASP Contract",
            legacy_contract_number="CONT-ASP",
            status="ACTIVE",
            effective_start_date="2025-01-01",
            provider_org=provider_org,
            network=network,
        )
        RefAspPricing.objects.create(
            hcpcs_code="J0129",
            quarter="2025-Q1",
            asp=Decimal("10.50"),
            payment_limit=Decimal("12.00"),
        )
        fs = FeeSchedule.objects.create(name="ASP Fallback", effective_date="2025-01-01")
        FeeScheduleRate.objects.create(fee_schedule=fs, code_id="J9999", rate_amount=Decimal("25.00"))
        rule = PricingRule.objects.create(
            contract=self.contract,
            rule_name="Drug ASP",
            specificity_score=10,
            methodology_code="ASP",
            base_fee_schedule=fs,
            multiplier=Decimal("1.0"),
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="J0129",
        )

    def test_asp_01_payment_limit_units(self):
        """ASP: payment_limit * units."""
        inp = PricingInput(
            procedure_code="J0129",
            billed_amount=Decimal("50.00"),
            units=2,
            service_date=date(2025, 2, 15),  # Q1 2025
        )
        result = self.engine.calculate_line(self.contract, inp)
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.allowed_amount, Decimal("24.00"))  # 12.00 * 2

    def test_asp_02_fallback_to_fee_schedule(self):
        """ASP: when no RefAspPricing, use base_rate from fee schedule if available."""
        r2 = PricingRule.objects.create(
            contract=self.contract,
            rule_name="Drug Other",
            specificity_score=5,
            methodology_code="ASP",
            base_fee_schedule=FeeSchedule.objects.get(name="ASP Fallback"),
            multiplier=Decimal("1.0"),
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=r2,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="J9999",
        )
        inp = PricingInput(
            procedure_code="J9999",
            billed_amount=Decimal("50.00"),
            units=1,
            service_date=date(2025, 2, 15),
        )
        result = self.engine.calculate_line(self.contract, inp)
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.allowed_amount, Decimal("25.00"))

    def test_asp_03_no_asp_found(self):
        """ASP: no RefAspPricing and no fee schedule rate returns NO_ASP_FOUND."""
        r3 = PricingRule.objects.create(
            contract=self.contract,
            rule_name="Drug Missing",
            specificity_score=1,
            methodology_code="ASP",
            multiplier=Decimal("1.0"),
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=r3,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="J0000",
        )
        inp = PricingInput(
            procedure_code="J0000",
            billed_amount=Decimal("100.00"),
            units=1,
            service_date=date(2025, 2, 15),
        )
        result = self.engine.calculate_line(self.contract, inp)
        self.assertEqual(result.status, PricingStatus.NO_ASP_FOUND)
        self.assertEqual(result.allowed_amount, Decimal("0.00"))
        self.assertIn("NO_ASP_FOUND", result.details)
