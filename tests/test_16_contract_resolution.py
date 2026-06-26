"""Phase 8: Contract resolution — hierarchical scoping and deterministic resolution."""
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
    RefProcedureCode,
    ClaimHeader,
    ClaimLine,
    ContractScope,
    ContractProviderParticipation,
)
from core.engine.orchestrator import PricingEngine
from core.engine.loader import resolve_contract_for_claim
from core.engine.types import PricingStatus
from core.engine.exceptions import ContractResolutionError, ContractResolutionTieError


class ContractResolutionTestMixin:
    """Shared setup: payer, provider, network, fee schedule, and a contract with one rule."""

    def setUp(self):
        self.engine = PricingEngine()
        self.payer_org = ProviderOrganization.objects.create(
            organization_id="PAYER-RES", name="Resolution Payer", tax_id="00-0000000"
        )
        self.provider_org = ProviderOrganization.objects.create(
            organization_id="PROV-RES", name="Resolution Provider", tax_id="11-1111111"
        )
        self.network = PayerNetwork.objects.create(
            network_id="NET-RES", network_name="Resolution Network", payer_org=self.payer_org
        )
        self.contract = ProviderContract.objects.create(
            contract_name="Resolution Contract",
            legacy_contract_number="CONT-RES",
            status="ACTIVE",
            effective_start_date=date(2025, 1, 1),
            provider_org=self.provider_org,
            network=self.network,
        )
        fs = FeeSchedule.objects.create(name="Res FS", effective_date=date(2025, 1, 1))
        RefProcedureCode.objects.create(
            code_id="99213", description="Office Visit", work_rvu=Decimal("0.97")
        )
        FeeScheduleRate.objects.create(
            fee_schedule=fs, code_id="99213", rate_amount=Decimal("100.00")
        )
        rule = PricingRule.objects.create(
            contract=self.contract,
            rule_name="RBRVS 99213",
            specificity_score=10,
            methodology_code="RBRVS",
            base_fee_schedule=fs,
            multiplier=Decimal("1.50"),
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="99213",
        )

    def _create_claim(self, service_date, lines_data, contract=None, provider_org=None, npi=None, line_of_business=None):
        """Create claim; contract/provider_org/npi/lob optional for resolution tests."""
        header = ClaimHeader.objects.create(
            contract=contract,
            service_date=service_date,
            claim_type="PROFESSIONAL",
            provider_org=provider_org,
            npi=npi or "",
            line_of_business=line_of_business or "",
        )
        for i, row in enumerate(lines_data):
            code, billed = row[0], row[1]
            cost = row[2] if len(row) > 2 else Decimal("0")
            units = row[3] if len(row) > 3 else 1
            seq = row[4] if len(row) > 4 else i
            ClaimLine.objects.create(
                claim=header,
                procedure_code=code,
                billed_amount=billed,
                cost_amount=cost,
                units=units,
                sequence=seq,
            )
        return header


class TestResolutionSkippedWhenContractSet(ContractResolutionTestMixin, TestCase):
    """Claim with explicit contract → resolution skipped, existing pricing used."""

    def test_explicit_contract_used(self):
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00"))],
            contract=self.contract,
        )
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.contract_id, str(self.contract.pk))
        # One line 99213: fee schedule rate 100 × multiplier 1.50 = 150
        self.assertEqual(result.total_allowed, Decimal("150.00"))


class TestResolutionSelectsCorrectScope(ContractResolutionTestMixin, TestCase):
    """Claim without contract → correct scope selected via participation + scope."""

    def test_resolved_contract_via_participation_and_scope(self):
        ContractProviderParticipation.objects.create(
            contract=self.contract,
            organization=self.provider_org,
            effective_start_date=date(2025, 1, 1),
            effective_end_date=date(2025, 12, 31),
        )
        ContractScope.objects.create(
            contract=self.contract,
            line_of_business="MED",
            priority=100,
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00"))],
            contract=None,
            provider_org=self.provider_org,
            line_of_business="MED",
        )
        resolved = resolve_contract_for_claim(claim)
        self.assertEqual(resolved.pk, self.contract.pk)
        result = self.engine.calculate_claim(claim)
        self.assertEqual(result.status, PricingStatus.SUCCESS)
        self.assertEqual(result.contract_id, str(self.contract.pk))


class TestResolutionPriorityOrdering(ContractResolutionTestMixin, TestCase):
    """Overlapping scopes with different priority → lower priority value wins."""

    def test_lower_priority_scope_wins(self):
        ContractProviderParticipation.objects.create(
            contract=self.contract,
            organization=self.provider_org,
            effective_start_date=date(2025, 1, 1),
        )
        ContractScope.objects.create(
            contract=self.contract,
            line_of_business="MED",
            priority=200,
        )
        ContractScope.objects.create(
            contract=self.contract,
            line_of_business="MED",
            priority=50,
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00"))],
            contract=None,
            provider_org=self.provider_org,
            line_of_business="MED",
        )
        resolved = resolve_contract_for_claim(claim)
        self.assertEqual(resolved.pk, self.contract.pk)
        # Best matching scope has priority 50 (lower than 200)
        scopes = list(ContractScope.objects.filter(contract=self.contract).order_by("priority"))
        self.assertGreaterEqual(len(scopes), 2)
        self.assertEqual(scopes[0].priority, 50)


class TestResolutionTieRaisesException(ContractResolutionTestMixin, TestCase):
    """Multiple contracts tied → ContractResolutionTieError raised."""

    def test_tie_raises_contract_resolution_tie_error(self):
        contract_b = ProviderContract.objects.create(
            contract_name="Resolution Contract B",
            status="ACTIVE",
            effective_start_date=date(2025, 1, 1),
            provider_org=self.provider_org,
            network=self.network,
        )
        fs = FeeSchedule.objects.first()
        rule_b = PricingRule.objects.create(
            contract=contract_b,
            rule_name="RBRVS 99213 B",
            specificity_score=10,
            methodology_code="RBRVS",
            base_fee_schedule=fs,
            multiplier=Decimal("1.50"),
            status=PricingRule.RuleStatus.ACTIVE,
        )
        PricingRuleCondition.objects.create(
            pricing_rule=rule_b,
            attribute_name="procedure_code",
            operator="EQ",
            attribute_value="99213",
        )
        ContractProviderParticipation.objects.create(
            contract=self.contract,
            organization=self.provider_org,
            effective_start_date=date(2025, 1, 1),
        )
        ContractProviderParticipation.objects.create(
            contract=contract_b,
            organization=self.provider_org,
            effective_start_date=date(2025, 1, 1),
        )
        ContractScope.objects.create(
            contract=self.contract,
            line_of_business="MED",
            priority=100,
        )
        ContractScope.objects.create(
            contract=contract_b,
            line_of_business="MED",
            priority=100,
        )
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00"))],
            contract=None,
            provider_org=self.provider_org,
            line_of_business="MED",
        )
        with self.assertRaises(ContractResolutionTieError):
            resolve_contract_for_claim(claim)


class TestParticipationDateBoundary(ContractResolutionTestMixin, TestCase):
    """Participation effective date boundary respected."""

    def test_before_start_no_match(self):
        ContractProviderParticipation.objects.create(
            contract=self.contract,
            organization=self.provider_org,
            effective_start_date=date(2025, 1, 1),
            effective_end_date=date(2025, 12, 31),
        )
        ContractScope.objects.create(
            contract=self.contract,
            line_of_business="MED",
            priority=100,
        )
        claim = self._create_claim(
            date(2024, 12, 31),
            [("99213", Decimal("200.00"))],
            contract=None,
            provider_org=self.provider_org,
            line_of_business="MED",
        )
        with self.assertRaises(ContractResolutionError):
            resolve_contract_for_claim(claim)

    def test_on_start_matches(self):
        ContractProviderParticipation.objects.create(
            contract=self.contract,
            organization=self.provider_org,
            effective_start_date=date(2025, 1, 1),
            effective_end_date=date(2025, 12, 31),
        )
        ContractScope.objects.create(
            contract=self.contract,
            line_of_business="MED",
            priority=100,
        )
        claim = self._create_claim(
            date(2025, 1, 1),
            [("99213", Decimal("200.00"))],
            contract=None,
            provider_org=self.provider_org,
            line_of_business="MED",
        )
        resolved = resolve_contract_for_claim(claim)
        self.assertEqual(resolved.pk, self.contract.pk)

    def test_after_end_no_match(self):
        ContractProviderParticipation.objects.create(
            contract=self.contract,
            organization=self.provider_org,
            effective_start_date=date(2025, 1, 1),
            effective_end_date=date(2025, 12, 31),
        )
        ContractScope.objects.create(
            contract=self.contract,
            line_of_business="MED",
            priority=100,
        )
        claim = self._create_claim(
            date(2026, 1, 1),
            [("99213", Decimal("200.00"))],
            contract=None,
            provider_org=self.provider_org,
            line_of_business="MED",
        )
        with self.assertRaises(ContractResolutionError):
            resolve_contract_for_claim(claim)

    def test_no_provider_or_npi_raises(self):
        claim = self._create_claim(
            date(2025, 6, 15),
            [("99213", Decimal("200.00"))],
            contract=None,
            provider_org=None,
            npi=None,
        )
        with self.assertRaises(ContractResolutionError):
            resolve_contract_for_claim(claim)
