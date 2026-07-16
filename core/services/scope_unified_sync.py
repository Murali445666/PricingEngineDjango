"""Keep ContractScopeUnified in sync when legacy scope tables are written (Gap E)."""
from __future__ import annotations

from core.models import ContractProductScope, ContractScope, ContractScopeUnified


def sync_from_contract_scope(scope: ContractScope) -> ContractScopeUnified:
    row, _ = ContractScopeUnified.objects.update_or_create(
        migration_source=ContractScopeUnified.MigrationSource.CONTRACT_SCOPE,
        migration_source_id=scope.id,
        defaults={
            'contract_id': scope.contract_id,
            'lob_code': scope.line_of_business or None,
            'product_id': None,
            'specialty_code_id': scope.specialty_code_id,
            'site_of_service': scope.site_of_service,
            'geo_id': scope.geo_id,
            'effective_date': None,
            'termination_date': None,
            'priority': scope.priority,
        },
    )
    return row


def sync_from_product_scope(ps: ContractProductScope) -> ContractScopeUnified:
    row, _ = ContractScopeUnified.objects.update_or_create(
        migration_source=ContractScopeUnified.MigrationSource.PRODUCT_SCOPE,
        migration_source_id=ps.id,
        defaults={
            'contract_id': ps.contract_id,
            'lob_code': ps.lob_code,
            'product_id': ps.product_id,
            'specialty_code_id': None,
            'site_of_service': None,
            'geo_id': None,
            'effective_date': ps.effective_date,
            'termination_date': ps.termination_date,
            'priority': 100,
        },
    )
    return row


def delete_unified_for_contract_scope(scope_id: int) -> None:
    ContractScopeUnified.objects.filter(
        migration_source=ContractScopeUnified.MigrationSource.CONTRACT_SCOPE,
        migration_source_id=scope_id,
    ).delete()


def delete_unified_for_product_scope(product_scope_id: int) -> None:
    ContractScopeUnified.objects.filter(
        migration_source=ContractScopeUnified.MigrationSource.PRODUCT_SCOPE,
        migration_source_id=product_scope_id,
    ).delete()


def upsert_unified_product_scope(
    *,
    contract_id: int,
    product_id: int,
    lob_code: str,
    effective_date,
    termination_date=None,
) -> ContractScopeUnified:
    """
    Write product scope directly to ContractScopeUnified (canonical resolver table).
    Uses a stable synthetic migration_source_id so seed/import paths stay idempotent
    without writing legacy ContractProductScope.
    """
    source_id = contract_id * 1_000_000 + product_id
    row, created = ContractScopeUnified.objects.update_or_create(
        migration_source=ContractScopeUnified.MigrationSource.PRODUCT_SCOPE,
        migration_source_id=source_id,
        defaults={
            'contract_id': contract_id,
            'lob_code': lob_code,
            'product_id': product_id,
            'specialty_code_id': None,
            'site_of_service': None,
            'geo_id': None,
            'effective_date': effective_date,
            'termination_date': termination_date,
            'priority': 100,
        },
    )
    return row, created
