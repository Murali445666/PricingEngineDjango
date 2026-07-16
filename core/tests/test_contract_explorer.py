"""
Step 12e: API tests for GET /api/contracts/<id>/explorer/.
Verifies response structure: contract, open_conflict_counts, versions with rules[], nested entities, CSV export.
"""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.models import (
    ProviderOrganization,
    PayerNetwork,
    ProviderContract,
    ContractVersion,
    PricingRule,
    ContractMethodology,
    ContractCarveout,
    ContractCapFloor,
    ContractBlendingRule,
    ContractStopLossRule,
    ContractOutlierRule,
)


class ContractExplorerAPITests(TestCase):
    """GET /api/contracts/<id>/explorer/ returns full contract tree or 404."""

    def setUp(self):
        self.org = ProviderOrganization.objects.create(
            organization_id="explorer-org",
            name="Explorer Test Org",
        )
        self.network = PayerNetwork.objects.create(
            network_id="explorer-net",
            network_name="Explorer Network",
            payer_org=self.org,
        )
        self.contract = ProviderContract.objects.create(
            contract_name="Explorer Contract",
            provider_org=self.org,
            network=self.network,
            status='ACTIVE',
            effective_start_date=date(2021, 1, 1),
            effective_end_date=None,
        )
        self.version = ContractVersion.objects.create(
            contract=self.contract,
            version_number=1,
            effective_start_date=date(2021, 1, 1),
            effective_end_date=None,
            status=ContractVersion.VersionStatus.ACTIVE,
        )

    def test_explorer_returns_404_for_nonexistent_contract(self):
        url = reverse("api-contract-explorer", kwargs={"pk": 999999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_explorer_returns_200_with_expected_root_keys(self):
        url = reverse("api-contract-explorer", kwargs={"pk": self.contract.contract_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("contract", data)
        self.assertEqual(data["contract"]["id"], self.contract.contract_id)
        self.assertEqual(data["contract"]["contract_name"], "Explorer Contract")
        self.assertIn("legacy_contract_number", data["contract"])
        self.assertIn("open_conflict_counts", data)
        self.assertIn("errors", data["open_conflict_counts"])
        self.assertIn("warnings", data["open_conflict_counts"])
        self.assertEqual(data["open_conflict_counts"]["errors"], 0)
        self.assertEqual(data["open_conflict_counts"]["warnings"], 0)
        self.assertIn("versions", data)
        self.assertIsInstance(data["versions"], list)

    def test_explorer_returns_versions_with_nested_arrays(self):
        url = reverse("api-contract-explorer", kwargs={"pk": self.contract.contract_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["versions"]), 1)
        ver = data["versions"][0]
        self.assertIn("version_id", ver)
        self.assertEqual(ver["version_id"], self.version.version_id)
        self.assertIn("version_number", ver)
        self.assertIn("status", ver)
        self.assertIn("effective_start_date", ver)
        self.assertIn("effective_end_date", ver)
        self.assertIn("methodologies", ver)
        self.assertIn("rules", ver)
        self.assertNotIn("pricing_rules", ver)
        self.assertIn("carveouts", ver)
        self.assertIn("cap_floors", ver)
        self.assertIn("blending_rules", ver)
        self.assertIn("stop_loss_rules", ver)
        self.assertIn("outlier_rules", ver)
        self.assertIsInstance(ver["methodologies"], list)
        self.assertIsInstance(ver["rules"], list)
        self.assertIsInstance(ver["carveouts"], list)
        self.assertIsInstance(ver["cap_floors"], list)
        self.assertIsInstance(ver["blending_rules"], list)
        self.assertIsInstance(ver["stop_loss_rules"], list)
        self.assertIsInstance(ver["outlier_rules"], list)

    def test_explorer_includes_pricing_rules_with_conditions(self):
        rule = PricingRule.objects.create(
            contract=self.contract,
            version=self.version,
            rule_name="Explorer Rule",
            rule_type="BASE",
            methodology_code="RBRVS",
            status="ACTIVE",
            effective_start_date=date(2021, 1, 1),
            effective_end_date=None,
        )
        url = reverse("api-contract-explorer", kwargs={"pk": self.contract.contract_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ver = response.json()["versions"][0]
        self.assertEqual(len(ver["rules"]), 1)
        self.assertEqual(ver["rules"][0]["rule_id"], rule.rule_id)
        self.assertEqual(ver["rules"][0]["rule_name"], "Explorer Rule")
        self.assertIn("conditions", ver["rules"][0])
        self.assertIsInstance(ver["rules"][0]["conditions"], list)

    def test_explorer_includes_carveouts(self):
        carve = ContractCarveout.objects.create(
            version=self.version,
            code_type="CPT",
            code_value="00100",
            carveout_methodology="PCT_BILLED",
            carveout_percentage=Decimal("80.00"),
            status=ContractVersion.VersionStatus.ACTIVE,
        )
        url = reverse("api-contract-explorer", kwargs={"pk": self.contract.contract_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ver = response.json()["versions"][0]
        self.assertEqual(len(ver["carveouts"]), 1)
        self.assertEqual(ver["carveouts"][0]["carveout_id"], carve.carveout_id)
        self.assertEqual(ver["carveouts"][0]["code_value"], "00100")

    def test_explorer_includes_cap_floors(self):
        cap = ContractCapFloor.objects.create(
            version=self.version,
            scope="CLAIM",
            cap_type="CAP",
            value=Decimal("10000.00"),
            priority=0,
            effective_start_date=date(2021, 1, 1),
            effective_end_date=None,
            status=ContractVersion.VersionStatus.ACTIVE,
        )
        url = reverse("api-contract-explorer", kwargs={"pk": self.contract.contract_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ver = response.json()["versions"][0]
        self.assertEqual(len(ver["cap_floors"]), 1)
        self.assertEqual(ver["cap_floors"][0]["cap_floor_id"], cap.cap_floor_id)
        self.assertEqual(ver["cap_floors"][0]["cap_type"], "CAP")

    def test_explorer_includes_blending_rules(self):
        blend = ContractBlendingRule.objects.create(
            version=self.version,
            blend_type="ADD",
            scope="CLAIM",
            primary_methodology="RBRVS",
            secondary_methodology="PCT_BILLED",
            blend_percentage=Decimal("10.00"),
            priority=0,
            effective_start_date=date(2021, 1, 1),
            effective_end_date=None,
            status=ContractVersion.VersionStatus.ACTIVE,
        )
        url = reverse("api-contract-explorer", kwargs={"pk": self.contract.contract_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ver = response.json()["versions"][0]
        self.assertEqual(len(ver["blending_rules"]), 1)
        self.assertEqual(ver["blending_rules"][0]["blending_rule_id"], blend.blending_rule_id)
        self.assertEqual(ver["blending_rules"][0]["blend_type"], "ADD")

    def test_explorer_includes_stop_loss_rules(self):
        stop = ContractStopLossRule.objects.create(
            contract=self.contract,
            version=self.version,
            cost_threshold=Decimal("50000.00"),
            reimbursement_percentage=Decimal("80.00"),
            priority=0,
            effective_start_date=date(2021, 1, 1),
            effective_end_date=None,
        )
        url = reverse("api-contract-explorer", kwargs={"pk": self.contract.contract_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ver = response.json()["versions"][0]
        self.assertEqual(len(ver["stop_loss_rules"]), 1)
        self.assertEqual(ver["stop_loss_rules"][0]["id"], stop.id)
        self.assertEqual(str(ver["stop_loss_rules"][0]["cost_threshold"]), "50000.00")

    def test_explorer_includes_outlier_rules(self):
        out = ContractOutlierRule.objects.create(
            contract=self.contract,
            version=self.version,
            threshold_amount=Decimal("25000.00"),
            threshold_scope="PER_CLAIM",
            reimbursement_percentage=Decimal("50.00"),
            priority=0,
            effective_start_date=date(2021, 1, 1),
            effective_end_date=None,
        )
        url = reverse("api-contract-explorer", kwargs={"pk": self.contract.contract_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ver = response.json()["versions"][0]
        self.assertEqual(len(ver["outlier_rules"]), 1)
        self.assertEqual(ver["outlier_rules"][0]["id"], out.id)
        self.assertEqual(str(ver["outlier_rules"][0]["threshold_amount"]), "25000.00")

    def test_explorer_includes_methodologies(self):
        meth = ContractMethodology.objects.create(
            contract=self.contract,
            version=self.version,
            methodology_type="RBRVS",
            effective_date=date(2021, 1, 1),
            termination_date=None,
            priority=0,
        )
        url = reverse("api-contract-explorer", kwargs={"pk": self.contract.contract_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        ver = response.json()["versions"][0]
        self.assertEqual(len(ver["methodologies"]), 1)
        self.assertEqual(ver["methodologies"][0]["id"], meth.id)
        self.assertEqual(ver["methodologies"][0]["methodology_type"], "RBRVS")

    def test_explorer_csv_format_returns_attachment(self):
        PricingRule.objects.create(
            contract=self.contract,
            version=self.version,
            rule_name="CSV Rule",
            rule_type="BASE",
            methodology_code="FLAT_RATE",
            status="ACTIVE",
            effective_start_date=date(2021, 1, 1),
            effective_end_date=None,
        )
        url = reverse("api-contract-explorer", kwargs={"pk": self.contract.contract_id})
        response = self.client.get(url, {"export": "csv"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        body = response.content.decode("utf-8")
        self.assertIn("contract_id", body)
        self.assertIn("CSV Rule", body)
        self.assertIn(str(self.contract.contract_id), body)

    def test_explorer_query_count_stays_bounded(self):
        """Prefetched tree should not devolve into per-rule queries."""
        for i in range(3):
            PricingRule.objects.create(
                contract=self.contract,
                version=self.version,
                rule_name=f"Bulk Rule {i}",
                rule_type="BASE",
                methodology_code="RBRVS",
                status="ACTIVE",
                effective_start_date=date(2021, 1, 1),
                effective_end_date=None,
            )
        url = reverse("api-contract-explorer", kwargs={"pk": self.contract.contract_id})
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertLess(
            len(ctx.captured_queries),
            24,
            msg=f"Too many DB queries for explorer (got {len(ctx.captured_queries)})",
        )
