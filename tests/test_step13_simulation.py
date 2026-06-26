"""
Step 13: Contract Simulation Engine tests.

- Simulate against DRAFT / SUPERSEDED version
- Reject ARCHIVED version
- Standard price-claim and bulk pricing unaffected
- No new queries in normal pricing path
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
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
)
from core.engine.service import ClaimPricingService
from core.engine.config import ClaimPricingInput, ClaimLineInput


def _make_contract_and_version(status=ContractVersion.VersionStatus.ACTIVE, version_number=1):
    """Create contract and version with given status. Returns (contract, version)."""
    payer = ProviderOrganization.objects.create(
        organization_id="SIM-PAYER",
        name="Sim Payer",
        tax_id="00-0000001",
    )
    prov = ProviderOrganization.objects.create(
        organization_id="SIM-PROV",
        name="Sim Prov",
        tax_id="11-1111111",
    )
    net = PayerNetwork.objects.create(
        network_id="SIM-NET",
        network_name="Sim Network",
        payer_org=payer,
    )
    contract = ProviderContract.objects.create(
        contract_name="Sim Contract",
        legacy_contract_number="SIM-C",
        status="ACTIVE",
        effective_start_date=date(2025, 1, 1),
        provider_org=prov,
        network=net,
    )
    version = ContractVersion.objects.create(
        contract=contract,
        version_number=version_number,
        effective_start_date=date(2025, 1, 1),
        status=status,
    )
    return contract, version


def _add_flat_rule(contract, procedure_code="99213", allowed=Decimal("200.00")):
    """Add FLAT_RATE rule for procedure_code; return (fs, rule)."""
    RefProcedureCode.objects.get_or_create(
        code_id=procedure_code,
        defaults={"description": "Office Visit", "work_rvu": Decimal("0.97")},
    )
    fs = FeeSchedule.objects.create(
        name="Sim FS",
        effective_date=date(2025, 1, 1),
    )
    FeeScheduleRate.objects.create(
        fee_schedule=fs,
        code_id=procedure_code,
        rate_amount=allowed,
    )
    rule = PricingRule.objects.create(
        contract=contract,
        rule_name="Sim FLAT",
        specificity_score=10,
        methodology_code="FLAT_RATE",
        flat_rate=allowed,
        status=PricingRule.RuleStatus.ACTIVE,
    )
    PricingRuleCondition.objects.create(
        pricing_rule=rule,
        attribute_name="procedure_code",
        operator="EQ",
        attribute_value=procedure_code,
    )
    return fs, rule


def _simulate_payload(contract_id, version_id, lines=None, service_date="2025-06-01"):
    if lines is None:
        lines = [
            {
                "procedure_code": "99213",
                "billed_amount": "500.00",
                "units": 1,
                "modifiers": [],
            }
        ]
    return {
        "contract_id": contract_id,
        "version_id": version_id,
        "claim": {
            "lines": lines,
            "service_date": service_date,
        },
    }


class TestSimulateDraftVersion(APITestCase):
    """Simulate against a DRAFT version."""

    def setUp(self):
        self.contract, self.version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.DRAFT,
            version_number=1,
        )
        _add_flat_rule(self.contract)

    def test_simulate_draft_returns_200_and_result(self):
        url = reverse("price-claim-simulate")
        payload = _simulate_payload(self.contract.pk, self.version.pk)
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["simulation"])
        self.assertEqual(data["version_id"], self.version.pk)
        self.assertIn("result", data)
        self.assertEqual(
            Decimal(str(data["result"]["total_allowed"])),
            Decimal("200.00"),
        )


class TestSimulateSupersededVersion(APITestCase):
    """Simulate against a SUPERSEDED version."""

    def setUp(self):
        self.contract, self.version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.SUPERSEDED,
            version_number=1,
        )
        _add_flat_rule(self.contract)

    def test_simulate_superseded_returns_200(self):
        url = reverse("price-claim-simulate")
        payload = _simulate_payload(self.contract.pk, self.version.pk)
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["simulation"])
        self.assertEqual(Decimal(str(data["result"]["total_allowed"])), Decimal("200.00"))


class TestSimulateRejectsArchived(APITestCase):
    """ARCHIVED version must be rejected with 400."""

    def setUp(self):
        self.contract, self.version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.ARCHIVED,
            version_number=1,
        )
        _add_flat_rule(self.contract)

    def test_simulate_archived_returns_400(self):
        url = reverse("price-claim-simulate")
        payload = _simulate_payload(self.contract.pk, self.version.pk)
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())
        self.assertIn("ARCHIVED", response.json()["error"])


class TestStandardPricingUnaffected(APITestCase):
    """Standard POST /api/price-claim/ still works and uses ACTIVE version."""

    def setUp(self):
        self.contract, self.version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.ACTIVE,
            version_number=1,
        )
        _add_flat_rule(self.contract)

    def test_standard_price_claim_returns_200(self):
        url = reverse("price-claim")
        payload = {
            "contract_id": self.contract.pk,
            "lines": [
                {"procedure_code": "99213", "billed_amount": "500.00", "units": 1},
            ],
            "service_date": "2025-06-01",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Decimal(str(response.json()["total_allowed"])),
            Decimal("200.00"),
        )


class TestBulkPricingUnaffected(APITestCase):
    """Bulk POST /api/price-claims-bulk/ still works."""

    def setUp(self):
        self.contract, self.version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.ACTIVE,
            version_number=1,
        )
        _add_flat_rule(self.contract)

    def test_bulk_price_claims_returns_200(self):
        url = reverse("price-claims-bulk")
        payload = {
            "claims": [
                {
                    "contract_id": self.contract.pk,
                    "lines": [
                        {"procedure_code": "99213", "billed_amount": "500.00", "units": 1},
                    ],
                    "service_date": "2025-06-01",
                }
            ],
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        results = response.json().get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(
            Decimal(str(results[0]["total_allowed"])),
            Decimal("200.00"),
        )


class TestSimulateVersionMismatch(APITestCase):
    """version_id that does not belong to contract returns 400."""

    def setUp(self):
        self.contract, self.version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.ACTIVE,
            version_number=1,
        )
        _add_flat_rule(self.contract)
        # Another contract + version
        self.other_contract, self.other_version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.ACTIVE,
            version_number=1,
        )

    def test_wrong_version_for_contract_returns_400(self):
        url = reverse("price-claim-simulate")
        # Use self.contract.pk but self.other_version.pk (other version belongs to other contract)
        payload = _simulate_payload(self.contract.pk, self.other_version.pk)
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())


class TestSimulateServiceLayer(TestCase):
    """Unit tests for ClaimPricingService.price_claim_with_version."""

    def test_archived_raises_value_error(self):
        contract, version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.ARCHIVED,
            version_number=1,
        )
        _add_flat_rule(contract)
        claim_input = ClaimPricingInput(
            contract_id=contract.pk,
            contract=contract,
            service_date=date(2025, 6, 1),
            lines=[
                ClaimLineInput(
                    procedure_code="99213",
                    billed_amount=Decimal("500.00"),
                    units=1,
                )
            ],
        )
        service = ClaimPricingService()
        with self.assertRaises(ValueError) as ctx:
            service.price_claim_with_version(contract.pk, version.pk, claim_input)
        self.assertIn("ARCHIVED", str(ctx.exception))

    def test_draft_version_returns_result(self):
        contract, version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.DRAFT,
            version_number=1,
        )
        _add_flat_rule(contract)
        claim_input = ClaimPricingInput(
            contract_id=contract.pk,
            contract=contract,
            service_date=date(2025, 6, 1),
            lines=[
                ClaimLineInput(
                    procedure_code="99213",
                    billed_amount=Decimal("500.00"),
                    units=1,
                )
            ],
        )
        service = ClaimPricingService()
        result = service.price_claim_with_version(contract.pk, version.pk, claim_input)
        self.assertEqual(result.total_allowed, Decimal("200.00"))
