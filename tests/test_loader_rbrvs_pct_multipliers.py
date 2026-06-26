"""
Loader multiplier propagation for RBRVS and PCT_BILLED under USE_REFERENCE_ONLY_PRICING.

Regression: reference-only path must not force conversion_factor / percent_of_billed to 1.0
when rule.multiplier encodes the contract discount.
"""
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
try:
    django.setup()
except RuntimeError:
    pass

from decimal import Decimal
from datetime import date

from django.test import TestCase

from core.models import (
    ProviderOrganization,
    PayerNetwork,
    ProviderContract,
    ContractVersion,
    FeeSchedule,
    FeeScheduleRate,
    PricingRule,
    PricingRuleCondition,
)
from core.engine.service import ClaimPricingService
from core.engine.config import ClaimPricingInput, ClaimLineInput


class TestRbrvsPctMultipliersWithReferenceOnly(TestCase):
    """Uses live settings (USE_REFERENCE_ONLY_PRICING typically True in config.settings)."""

    SERVICE_DATE = date(2026, 6, 1)

    def setUp(self):
        payer = ProviderOrganization.objects.create(
            organization_id="PAYER-RM", name="RM Payer", tax_id="11-0000001"
        )
        provider = ProviderOrganization.objects.create(
            organization_id="PROV-RM", name="RM Provider", tax_id="22-0000002"
        )
        network = PayerNetwork.objects.create(
            network_id="NET-RM", network_name="RM Network", payer_org=payer
        )
        self.contract = ProviderContract.objects.create(
            contract_name="Multiplier test",
            legacy_contract_number="RM-TEST",
            status="ACTIVE",
            effective_start_date=date(2026, 1, 1),
            provider_org=provider,
            network=network,
        )
        self.version = ContractVersion.objects.create(
            contract=self.contract,
            version_number=1,
            effective_start_date=date(2026, 1, 1),
            effective_end_date=date(2026, 12, 31),
            status=ContractVersion.VersionStatus.ACTIVE,
        )
        self.fs = FeeSchedule.objects.create(
            name="RM FS", effective_date=date(2026, 1, 1)
        )
        FeeScheduleRate.objects.create(
            fee_schedule=self.fs,
            code_id="99213",
            rate_amount=Decimal("100.00"),
            effective_start_date=date(2026, 1, 1),
            effective_end_date=date(2026, 12, 31),
            year=2026,
        )

    def test_rbrvs_fee_schedule_rate_times_rule_multiplier(self):
        rule = PricingRule.objects.create(
            contract=self.contract,
            version=self.version,
            rule_name="R1",
            rule_type="BASE",
            methodology_code="RBRVS",
            base_fee_schedule=self.fs,
            multiplier=Decimal("1.5"),
            status=PricingRule.RuleStatus.ACTIVE,
            effective_start_date=date(2026, 1, 1),
            effective_end_date=date(2026, 12, 31),
            specificity_score=10,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="99213",
        )
        service = ClaimPricingService()
        result = service.price_claim(
            ClaimPricingInput(
                contract=self.contract,
                contract_id=self.contract.pk,
                service_date=self.SERVICE_DATE,
                lines=[
                    ClaimLineInput(
                        procedure_code="99213",
                        billed_amount=Decimal("200"),
                        units=1,
                    )
                ],
            )
        )
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.lines[0].allowed_amount, Decimal("150.00"))

    def test_pct_billed_rule_multiplier_applied(self):
        rule = PricingRule.objects.create(
            contract=self.contract,
            version=self.version,
            rule_name="R1",
            rule_type="BASE",
            methodology_code="PCT_BILLED",
            multiplier=Decimal("0.8"),
            status=PricingRule.RuleStatus.ACTIVE,
            effective_start_date=date(2026, 1, 1),
            effective_end_date=date(2026, 12, 31),
            specificity_score=10,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="99213",
        )
        service = ClaimPricingService()
        result = service.price_claim(
            ClaimPricingInput(
                contract=self.contract,
                contract_id=self.contract.pk,
                service_date=self.SERVICE_DATE,
                lines=[
                    ClaimLineInput(
                        procedure_code="99213",
                        billed_amount=Decimal("200"),
                        units=1,
                    )
                ],
            )
        )
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.lines[0].allowed_amount, Decimal("160.00"))

    def test_flat_rate_rule_flat_amount_when_reference_only_empty(self):
        """DEMO_FLAT-style: rule.flat_rate only (no PerDiem/override) must price under USE_REFERENCE_ONLY."""
        rule = PricingRule.objects.create(
            contract=self.contract,
            version=self.version,
            rule_name="R1",
            rule_type="BASE",
            methodology_code="FLAT_RATE",
            flat_rate=Decimal("250.00"),
            status=PricingRule.RuleStatus.ACTIVE,
            effective_start_date=date(2026, 1, 1),
            effective_end_date=date(2026, 12, 31),
            specificity_score=10,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="00100",
        )
        service = ClaimPricingService()
        result = service.price_claim(
            ClaimPricingInput(
                contract=self.contract,
                contract_id=self.contract.pk,
                service_date=self.SERVICE_DATE,
                lines=[
                    ClaimLineInput(
                        procedure_code="00100",
                        billed_amount=Decimal("300"),
                        units=1,
                    )
                ],
            )
        )
        self.assertEqual(len(result.lines), 1)
        self.assertEqual(result.lines[0].allowed_amount, Decimal("250.00"))
