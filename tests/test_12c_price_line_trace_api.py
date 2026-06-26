"""Step 12c: POST /api/price-line/ includes trace_logs for UI simulate panel."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIClient

from core.models import (
    ProviderContract,
    ProviderOrganization,
    PayerNetwork,
    PricingRule,
    PricingRuleCondition,
    RefProcedureCode,
    FeeSchedule,
    FeeScheduleRate,
)


def _contract_with_flat_rule():
    payer = ProviderOrganization.objects.create(
        organization_id="PL-12C-PAYER",
        name="PL Payer",
        tax_id="22-2222222",
    )
    prov = ProviderOrganization.objects.create(
        organization_id="PL-12C-PROV",
        name="PL Prov",
        tax_id="33-3333333",
    )
    net = PayerNetwork.objects.create(
        network_id="PL-12C-NET",
        network_name="PL Net",
        payer_org=payer,
    )
    contract = ProviderContract.objects.create(
        contract_name="PL Trace Contract",
        legacy_contract_number="PL-12C",
        status="ACTIVE",
        effective_start_date=date(2025, 1, 1),
        provider_org=prov,
        network=net,
    )
    RefProcedureCode.objects.get_or_create(
        code_id="99213",
        defaults={"description": "Office Visit", "work_rvu": Decimal("0.97")},
    )
    fs = FeeSchedule.objects.create(name="PL FS", effective_date=date(2025, 1, 1))
    FeeScheduleRate.objects.create(
        fee_schedule=fs,
        code_id="99213",
        rate_amount=Decimal("100.00"),
    )
    rule = PricingRule.objects.create(
        contract=contract,
        rule_name="PL Flat",
        specificity_score=10,
        methodology_code="FLAT_RATE",
        flat_rate=Decimal("100.00"),
        status=PricingRule.RuleStatus.ACTIVE,
    )
    PricingRuleCondition.objects.create(
        pricing_rule=rule,
        attribute_name="procedure_code",
        operator="EQ",
        attribute_value="99213",
    )
    return contract


class PriceLineTraceLogsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.contract = _contract_with_flat_rule()

    def test_price_line_response_includes_trace_logs_list(self):
        url = reverse("api-price-line")
        res = self.client.post(
            url,
            {
                "contract_id": str(self.contract.pk),
                "procedure_code": "99213",
                "billed_amount": "150.00",
                "units": 1,
                "modifiers": [],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("trace_logs", body)
        self.assertIsInstance(body["trace_logs"], list)
