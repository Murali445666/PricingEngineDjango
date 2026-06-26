"""
Step 14a: FEATURE_TIERED_RESOLUTION — tier sort, product filter, TierMultiplier loader, simulate API.
"""
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from core.models import (
    ProviderContract,
    ProviderOrganization,
    PayerNetwork,
    ContractVersion,
    FeeSchedule,
    FeeScheduleRate,
    PricingRule,
    PricingRuleCondition,
    RefProcedureCode,
    TierMultiplier,
)
from core.engine.resolver import StrictRuleResolver, _rule_tier_priority
from core.engine.loader import PricingDataLoader, build_contract_pricing_config_from_db
from core.engine.types import PricingInput, PricingTrace


def _make_contract_version(
    status=ContractVersion.VersionStatus.ACTIVE,
    version_number=1,
    *,
    product_id=None,
    tier_priority=0,
    pricing_engine_mode=None,
):
    payer = ProviderOrganization.objects.create(
        organization_id="T14-PAYER",
        name="T14 Payer",
        tax_id="00-0000002",
    )
    prov = ProviderOrganization.objects.create(
        organization_id="T14-PROV",
        name="T14 Prov",
        tax_id="11-1111112",
    )
    net = PayerNetwork.objects.create(
        network_id="T14-NET",
        network_name="T14 Network",
        payer_org=payer,
    )
    contract = ProviderContract.objects.create(
        contract_name="T14 Contract",
        legacy_contract_number="T14-C",
        status="ACTIVE",
        effective_start_date=date(2025, 1, 1),
        provider_org=prov,
        network=net,
    )
    pe_mode = pricing_engine_mode or ContractVersion.PricingEngineMode.LEGACY
    version = ContractVersion.objects.create(
        contract=contract,
        version_number=version_number,
        effective_start_date=date(2025, 1, 1),
        status=status,
        product_id=product_id,
        tier_priority=tier_priority,
        pricing_engine_mode=pe_mode,
    )
    return contract, version


class TestTierSortKey(TestCase):
    """Resolver list ordering: higher tier_priority before specificity when flag is on (tuple compare)."""

    def test_higher_tier_priority_sorts_before_lower_same_version_bucket(self):
        r_hi = Mock(version_id=1, specificity_score=10)
        r_hi.version = SimpleNamespace(tier_priority=100)
        r_lo = Mock(version_id=1, specificity_score=10)
        r_lo.version = SimpleNamespace(tier_priority=50)
        k_hi = (0, -_rule_tier_priority(r_hi), -(r_hi.specificity_score or 0))
        k_lo = (0, -_rule_tier_priority(r_lo), -(r_lo.specificity_score or 0))
        self.assertLess(k_hi, k_lo)

    @override_settings(FEATURE_TIERED_RESOLUTION=False)
    def test_flag_off_legacy_sort_ignores_tier_priority(self):
        r_hi = Mock(version_id=1, specificity_score=10)
        r_hi.version = SimpleNamespace(tier_priority=100)
        r_lo = Mock(version_id=1, specificity_score=10)
        r_lo.version = SimpleNamespace(tier_priority=50)
        # Legacy: (version_bucket, -spec) only
        k_hi = (0, -(r_hi.specificity_score or 0))
        k_lo = (0, -(r_lo.specificity_score or 0))
        self.assertEqual(k_hi, k_lo)


class TestTierProductFilterResolver(TestCase):
    @override_settings(FEATURE_TIERED_RESOLUTION=True)
    def test_product_mismatch_excludes_version_scoped_rule(self):
        contract, version = _make_contract_version(product_id="PPO")
        RefProcedureCode.objects.get_or_create(
            code_id="99213",
            defaults={"description": "Visit", "work_rvu": Decimal("0.97")},
        )
        rule = PricingRule.objects.create(
            contract=contract,
            version=version,
            rule_name="Tier PPO rule",
            rule_type="BASE",
            specificity_score=100,
            methodology_code="FLAT_RATE",
            flat_rate=Decimal("300.00"),
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="99213",
        )
        config = build_contract_pricing_config_from_db(contract, version, date(2025, 6, 1))
        trace = PricingTrace()
        req = PricingInput(
            procedure_code="99213",
            billed_amount=Decimal("500"),
            service_date=date(2025, 6, 1),
            product_id="HMO",
        )
        resolver = StrictRuleResolver(contract, version=version, config=config)
        matched = resolver.resolve_for_stage(req, trace, "BASE")
        self.assertEqual(matched, [])

    @override_settings(FEATURE_TIERED_RESOLUTION=False)
    def test_flag_off_product_mismatch_still_evaluates_rule(self):
        contract, version = _make_contract_version(product_id="PPO")
        RefProcedureCode.objects.get_or_create(
            code_id="99213",
            defaults={"description": "Visit", "work_rvu": Decimal("0.97")},
        )
        rule = PricingRule.objects.create(
            contract=contract,
            version=version,
            rule_name="Tier PPO rule",
            rule_type="BASE",
            specificity_score=100,
            methodology_code="FLAT_RATE",
            flat_rate=Decimal("300.00"),
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="99213",
        )
        config = build_contract_pricing_config_from_db(contract, version, date(2025, 6, 1))
        trace = PricingTrace()
        req = PricingInput(
            procedure_code="99213",
            billed_amount=Decimal("500"),
            service_date=date(2025, 6, 1),
            product_id="HMO",
        )
        resolver = StrictRuleResolver(contract, version=version, config=config)
        matched = resolver.resolve_for_stage(req, trace, "BASE")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].rule_id, rule.rule_id)


class TestTierMultiplierLoader(TestCase):
    @override_settings(FEATURE_TIERED_RESOLUTION=True)
    def test_tier_multiplier_used_for_pct_billed_when_no_rule_multiplier(self):
        contract, version = _make_contract_version()
        RefProcedureCode.objects.get_or_create(
            code_id="99213",
            defaults={"description": "Visit", "work_rvu": Decimal("0.97")},
        )
        rule = PricingRule.objects.create(
            contract=contract,
            version=version,
            rule_name="Pct",
            rule_type="BASE",
            specificity_score=50,
            methodology_code="PCT_BILLED",
            multiplier=1.0,
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="99213",
        )
        TierMultiplier.objects.create(
            contract=contract,
            version=version,
            product_id="ACME",
            network_id=None,
            multiplier=Decimal("0.7500"),
            effective_start_date=date(2025, 1, 1),
        )
        inp = PricingInput(
            procedure_code="99213",
            billed_amount=Decimal("200.00"),
            service_date=date(2025, 6, 1),
            product_id="ACME",
        )
        trace = PricingTrace()
        ctx = PricingDataLoader().load_context(inp, rule, version=version, config=None, trace=trace)
        self.assertEqual(ctx.percent_of_billed, Decimal("0.7500"))
        self.assertTrue(any("TIER_MULTIPLIER" in x for x in trace.logs))


class TestSimulateTierIntegration(APITestCase):
    @override_settings(FEATURE_TIERED_RESOLUTION=True)
    def test_price_claim_simulate_product_id_matches_tier_multiplier(self):
        contract, version = _make_contract_version(
            status=ContractVersion.VersionStatus.DRAFT,
            product_id="PPO",
            tier_priority=10,
            pricing_engine_mode=ContractVersion.PricingEngineMode.STAGED,
        )
        RefProcedureCode.objects.get_or_create(
            code_id="99213",
            defaults={"description": "Visit", "work_rvu": Decimal("0.97")},
        )
        rule = PricingRule.objects.create(
            contract=contract,
            version=version,
            rule_name="Pct staged",
            rule_type="BASE",
            specificity_score=80,
            methodology_code="PCT_BILLED",
            multiplier=1.0,
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="99213",
        )
        TierMultiplier.objects.create(
            contract=contract,
            version=version,
            product_id="PPO",
            multiplier=Decimal("0.8000"),
            effective_start_date=date(2025, 1, 1),
        )
        url = reverse("price-claim-simulate")
        payload = {
            "contract_id": contract.pk,
            "version_id": version.pk,
            "claim": {
                "lines": [
                    {
                        "procedure_code": "99213",
                        "billed_amount": "100.00",
                        "units": 1,
                        "modifiers": [],
                    }
                ],
                "service_date": "2025-06-01",
                "product_id": "PPO",
            },
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        result = response.data["result"]
        lines = result["lines"]
        self.assertEqual(len(lines), 1)
        # 100 * 0.80 = 80
        self.assertEqual(Decimal(str(lines[0]["allowed_amount"])), Decimal("80.00"))
