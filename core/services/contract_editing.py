"""Helpers for DRAFT-safe contract authoring (including amendment drafts on ACTIVE contracts)."""
from __future__ import annotations

from core.models import ContractVersion, ProviderContract


def contract_has_draft_version(contract: ProviderContract) -> bool:
    return ContractVersion.objects.filter(
        contract=contract,
        status=ContractVersion.VersionStatus.DRAFT,
    ).exists()


def contract_is_editable(contract: ProviderContract) -> bool:
    """True when roster/scope/rate-exhibit mutations are allowed."""
    if contract.status == 'DRAFT':
        return True
    return contract_has_draft_version(contract)
