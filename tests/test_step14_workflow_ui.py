"""
Step 14: Functional Simulation Workflow UI — integration tests.

- GET workflow page → 200 (staff)
- POST simulation → 200 and result
- Compare mode → difference shown
- Activate/Archive buttons (API) work; redirect with message
- Non-staff → forbidden (302 redirect to login)
- Standard pricing and bulk pricing unchanged
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from rest_framework.test import APIClient

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

User = get_user_model()


def _make_contract_and_version(status=ContractVersion.VersionStatus.ACTIVE, version_number=1):
    """Create contract and version. Returns (contract, version)."""
    payer = ProviderOrganization.objects.create(
        organization_id="WF-PAYER",
        name="WF Payer",
        tax_id="00-0000002",
    )
    prov = ProviderOrganization.objects.create(
        organization_id="WF-PROV",
        name="WF Prov",
        tax_id="22-2222222",
    )
    net = PayerNetwork.objects.create(
        network_id="WF-NET",
        network_name="WF Network",
        payer_org=payer,
    )
    contract = ProviderContract.objects.create(
        contract_name="WF Contract",
        legacy_contract_number="WF-C",
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
    RefProcedureCode.objects.get_or_create(
        code_id=procedure_code,
        defaults={"description": "Office Visit", "work_rvu": Decimal("0.97")},
    )
    FeeSchedule.objects.create(name="WF FS", effective_date=date(2025, 1, 1))
    fs = FeeSchedule.objects.get(name="WF FS")
    FeeScheduleRate.objects.create(fee_schedule=fs, code_id=procedure_code, rate_amount=allowed)
    rule = PricingRule.objects.create(
        contract=contract,
        rule_name="WF FLAT",
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


def _claim_json():
    return '{"lines": [{"procedure_code": "99213", "billed_amount": "500.00", "units": 1}], "service_date": "2025-06-01"}'


class TestWorkflowGET(TestCase):
    """GET workflow page returns 200 for staff user."""

    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(username="staff", password="test", is_staff=True)
        self.contract, self.version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.DRAFT,
        )

    def test_get_workflow_page_200(self):
        self.client.login(username="staff", password="test")
        url = reverse(
            "contract-version-workflow",
            kwargs={"contract_id": self.contract.pk, "version_id": self.version.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Version details", response.content)
        self.assertIn(b"Simulation", response.content)
        self.assertIn(str(self.version.version_id).encode(), response.content)


class TestWorkflowSimulationPOST(TestCase):
    """POST simulation with valid claim returns 200 and result."""

    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(username="staff2", password="test", is_staff=True)
        self.contract, self.version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.DRAFT,
        )
        _add_flat_rule(self.contract)

    def test_post_simulation_200_and_result(self):
        self.client.login(username="staff2", password="test")
        url = reverse(
            "contract-version-workflow",
            kwargs={"contract_id": self.contract.pk, "version_id": self.version.pk},
        )
        self.client.get(url)
        csrf = self.client.cookies.get("csrftoken")
        csrf = csrf.value if csrf else ""
        response = self.client.post(
            url,
            {"claim_json": _claim_json()},
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Simulation result", response.content)
        self.assertIn(b"200.00", response.content)
        self.assertIn(b"Line breakdown", response.content)


class TestWorkflowCompareMode(TestCase):
    """Compare mode shows ACTIVE comparison and difference."""

    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(username="staff3", password="test", is_staff=True)
        self.contract, self.draft_version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.DRAFT,
            version_number=1,
        )
        _add_flat_rule(self.contract)
        self.active_version = ContractVersion.objects.create(
            contract=self.contract,
            version_number=2,
            effective_start_date=date(2025, 1, 1),
            status=ContractVersion.VersionStatus.ACTIVE,
        )

    def test_compare_shows_difference(self):
        self.client.login(username="staff3", password="test")
        url = reverse(
            "contract-version-workflow",
            kwargs={"contract_id": self.contract.pk, "version_id": self.draft_version.pk},
        )
        self.client.get(url)
        csrf = self.client.cookies.get("csrftoken", "").value
        response = self.client.post(
            url,
            {
                "claim_json": _claim_json(),
                "compare_to_active": "on",
            },
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ACTIVE comparison", response.content)
        self.assertIn(b"Difference", response.content)


class TestWorkflowActivateRedirect(TestCase):
    """Activate API works; workflow page shows success when opened with ?msg=activated."""

    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(username="staff4", password="test", is_staff=True)
        self.contract, self.version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.DRAFT,
        )

    def test_activate_api_200(self):
        """POST to activate endpoint returns 200 (button uses this then redirects)."""
        self.client.login(username="staff4", password="test")
        self.client.get(reverse("contract-version-workflow", kwargs={"contract_id": self.contract.pk, "version_id": self.version.pk}))
        csrf = self.client.cookies.get("csrftoken")
        csrf = csrf.value if csrf else ""
        activate_url = reverse("api-contract-version-activate", kwargs={"pk": self.version.pk})
        response = self.client.post(activate_url, {}, HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 200)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, ContractVersion.VersionStatus.ACTIVE)

    def test_workflow_with_msg_activated_shows_success(self):
        self.client.login(username="staff4", password="test")
        url = reverse(
            "contract-version-workflow",
            kwargs={"contract_id": self.contract.pk, "version_id": self.version.pk},
        )
        response = self.client.get(url + "?msg=activated")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"activated successfully", response.content)


class TestWorkflowArchiveRedirect(TestCase):
    """Archive API works; workflow shows success with ?msg=archived."""

    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(username="staff5", password="test", is_staff=True)
        self.contract, self.version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.DRAFT,
        )

    def test_archive_api_200(self):
        self.client.login(username="staff5", password="test")
        self.client.get(reverse("contract-version-workflow", kwargs={"contract_id": self.contract.pk, "version_id": self.version.pk}))
        csrf = self.client.cookies.get("csrftoken")
        csrf = csrf.value if csrf else ""
        archive_url = reverse("api-contract-version-archive", kwargs={"pk": self.version.pk})
        response = self.client.post(archive_url, {}, HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code, 200)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, ContractVersion.VersionStatus.ARCHIVED)

    def test_workflow_with_msg_archived_shows_success(self):
        self.client.login(username="staff5", password="test")
        url = reverse(
            "contract-version-workflow",
            kwargs={"contract_id": self.contract.pk, "version_id": self.version.pk},
        )
        response = self.client.get(url + "?msg=archived")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"archived successfully", response.content)


class TestWorkflowNonStaffForbidden(TestCase):
    """Non-staff user cannot access workflow (302 redirect to login or 403)."""

    def setUp(self):
        self.client = Client()
        self.non_staff = User.objects.create_user(username="user", password="test", is_staff=False)
        self.contract, self.version = _make_contract_and_version()

    def test_non_staff_get_redirect_or_403(self):
        self.client.login(username="user", password="test")
        url = reverse(
            "contract-version-workflow",
            kwargs={"contract_id": self.contract.pk, "version_id": self.version.pk},
        )
        response = self.client.get(url)
        self.assertIn(response.status_code, (302, 403))

    def test_anonymous_redirect(self):
        url = reverse(
            "contract-version-workflow",
            kwargs={"contract_id": self.contract.pk, "version_id": self.version.pk},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)


class TestStandardPricingUnaffected(TestCase):
    """Confirm standard price-claim endpoint unchanged."""

    def setUp(self):
        self.contract, self.version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.ACTIVE,
        )
        _add_flat_rule(self.contract)
        self.api = APIClient()

    def test_standard_price_claim_200(self):
        url = reverse("price-claim")
        response = self.api.post(
            url,
            {
                "contract_id": self.contract.pk,
                "lines": [{"procedure_code": "99213", "billed_amount": "500.00", "units": 1}],
                "service_date": "2025-06-01",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(str(response.json()["total_allowed"])), Decimal("200.00"))


class TestBulkPricingUnaffected(TestCase):
    """Confirm bulk pricing endpoint unchanged."""

    def setUp(self):
        self.contract, self.version = _make_contract_and_version(
            status=ContractVersion.VersionStatus.ACTIVE,
        )
        _add_flat_rule(self.contract)
        self.api = APIClient()

    def test_bulk_price_claims_200(self):
        url = reverse("price-claims-bulk")
        response = self.api.post(
            url,
            {
                "claims": [
                    {
                        "contract_id": self.contract.pk,
                        "lines": [{"procedure_code": "99213", "billed_amount": "500.00", "units": 1}],
                        "service_date": "2025-06-01",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        results = response.json().get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(Decimal(str(results[0]["total_allowed"])), Decimal("200.00"))
