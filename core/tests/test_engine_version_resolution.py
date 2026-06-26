"""
Tests for contract version resolution used by the pricing engine (simulate path).
Ensures the engine uses the version specified in the request (contract_id + version_id)
and returns 400 when that version cannot be loaded (no silent fallback).
"""
from django.test import TestCase

from core.engine.loader import resolve_contract_version


class ResolveContractVersionTests(TestCase):
    """resolve_contract_version(contract_id, version_id) must use version_id (PK), not id."""

    def test_resolve_contract_version_raises_when_version_not_found(self):
        """When version_id does not exist (or wrong contract), must raise ValueError (no fallback)."""
        with self.assertRaises(ValueError) as ctx:
            resolve_contract_version(contract_id=99999, version_id=99999)
        self.assertIn("99999", str(ctx.exception))
        self.assertIn("not found", str(ctx.exception).lower())

    def test_resolve_contract_version_raises_when_version_belongs_to_other_contract(self):
        """When version exists but for a different contract_id, must raise ValueError."""
        from datetime import date
        from core.models import (
            ProviderOrganization,
            PayerNetwork,
            ProviderContract,
            ContractVersion,
        )

        org = ProviderOrganization.objects.create(
            organization_id="test-org-ver",
            name="Test Org",
        )
        network = PayerNetwork.objects.create(
            network_id="test-net-ver",
            network_name="Test Network",
            payer_org=org,
        )
        contract = ProviderContract.objects.create(
            contract_name="Test Contract",
            provider_org=org,
            network=network,
            effective_start_date=date(2020, 1, 1),
            effective_end_date=None,
        )
        version = ContractVersion.objects.create(
            contract=contract,
            version_number=1,
            effective_start_date=date(2020, 1, 1),
            effective_end_date=None,
            status=ContractVersion.VersionStatus.ACTIVE,
        )
        with self.assertRaises(ValueError) as ctx:
            resolve_contract_version(contract_id=contract.pk + 99999, version_id=version.version_id)
        self.assertIn("not found", str(ctx.exception).lower())

    def test_resolve_contract_version_returns_version_by_version_id(self):
        """When version exists for the given contract, returns it (using version_id as PK)."""
        from datetime import date
        from core.models import (
            ProviderOrganization,
            PayerNetwork,
            ProviderContract,
            ContractVersion,
        )

        org = ProviderOrganization.objects.create(
            organization_id="test-org-ver2",
            name="Test Org 2",
        )
        network = PayerNetwork.objects.create(
            network_id="test-net-ver2",
            network_name="Test Network 2",
            payer_org=org,
        )
        contract = ProviderContract.objects.create(
            contract_name="Test Contract 2",
            provider_org=org,
            network=network,
            effective_start_date=date(2020, 1, 1),
            effective_end_date=None,
        )
        version = ContractVersion.objects.create(
            contract=contract,
            version_number=1,
            effective_start_date=date(2020, 1, 1),
            effective_end_date=None,
            status=ContractVersion.VersionStatus.ACTIVE,
        )
        resolved = resolve_contract_version(contract_id=contract.pk, version_id=version.version_id)
        self.assertEqual(resolved.version_id, version.version_id)
        self.assertEqual(resolved.contract_id, contract.pk)
