"""
Step 12e: Contract Explorer — read-only full contract tree for the analyst UI.

Uses select_related/prefetch_related to keep query count small (e.g. ≤15 for
a contract with 5 versions and 50 rules).
"""
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch

from core.models import (
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


def get_full_contract(contract_id: int) -> ProviderContract:
    """
    Load a contract by id with all explorer data in a bounded number of queries.

    Returns the contract instance with prefetched:
    - validation_results (for open_error_count / open_warning_count)
    - versions, each with:
      - methodologies
      - pricing_rules + conditions
      - carveouts
      - cap_floors
      - blending_rules
      - stop_loss_rules
      - outlier_rules

    Raises Http404 if contract does not exist.
    """
    versions_qs = (
        ContractVersion.objects.order_by('-version_number')
        .prefetch_related(
            'methodologies',
            Prefetch(
                'pricing_rules',
                queryset=PricingRule.objects.prefetch_related('conditions').order_by('rule_id'),
            ),
            'carveouts',
            'cap_floors',
            'blending_rules',
            'stop_loss_rules',
            'outlier_rules',
        )
    )
    contract = get_object_or_404(
        ProviderContract.objects.prefetch_related(
            'validation_results',
            Prefetch('versions', queryset=versions_qs),
        ),
        pk=contract_id,
    )
    return contract
