from datetime import date

from django.db import models

from core.models import ContractProductScope, ContractScope, ProviderContract


class ContractResolutionError(Exception):
    """Raised when no contract can be resolved for the given context."""

    def __init__(self, message: str, is_oon: bool = False):
        super().__init__(message)
        self.is_oon = is_oon


class ContractResolver:
    """
    Resolves the best-matching ProviderContract for a given
    (org_id, network_id, lob, service_date) combination.

    Resolution specificity order (most → least specific):
      1. org + network + lob + product (ContractProductScope with product FK)
      2. org + network + lob (ContractProductScope lob_code, OR ContractScope
         line_of_business, OR ProviderContract.line_of_business — all checked)
      3. org + network (no LOB scoping)
      4. org only (fallback)
    Network resolution: products.Network.legacy_payer_network bridges to
    core.PayerNetwork. If legacy_payer_network is null, network resolution
    returns no results — Network.clean() warns on this at save time.
    Returns the contract_id of the first match at the highest specificity level.
    Raises ContractResolutionError if no match found.
    """

    def resolve(
        self,
        org_id: str,
        network_id: int | None,
        lob: str | None,
        service_date: date,
        product_id: int | None = None,
    ) -> int:
        """
        Returns the contract_id of the best-matching contract.
        Raises ContractResolutionError(is_oon=True) if org exists but no contract matches.
        Raises ContractResolutionError(is_oon=False) if org not found.
        """
        if not org_id:
            raise ContractResolutionError(
                'Organization not found',
                is_oon=False,
            )

        qs = ProviderContract.objects.filter(
            provider_org_id=org_id,
            effective_start_date__lte=service_date,
        ).filter(
            models.Q(effective_end_date__isnull=True)
            | models.Q(effective_end_date__gte=service_date)
        )

        if not qs.exists():
            raise ContractResolutionError(
                f'No contracts found for org {org_id}',
                is_oon=False,
            )

        if network_id is not None and product_id is not None and lob is not None:
            candidate = self._resolve_with_product_scope(
                qs, network_id, lob, product_id, service_date
            )
            if candidate:
                return candidate

        if network_id is not None and lob is not None:
            candidate = self._resolve_with_lob(qs, network_id, lob, service_date)
            if candidate:
                return candidate

        if network_id is not None:
            candidate = self._resolve_network_only(qs, network_id, service_date)
            if candidate:
                return candidate

        if network_id is None:
            candidate = self._resolve_org_only(qs, service_date)
            if candidate:
                return candidate

        raise ContractResolutionError(
            f'No matching contract for org={org_id} network={network_id} lob={lob}',
            is_oon=True,
        )

    def _resolve_with_product_scope(
        self, qs, network_id, lob, product_id, service_date
    ):
        """Contracts scoped to this exact product."""
        scoped_ids = ContractProductScope.objects.filter(
            product_id=product_id,
            lob_code=lob,
        ).filter(
            models.Q(effective_date__isnull=True)
            | models.Q(effective_date__lte=service_date)
        ).filter(
            models.Q(termination_date__isnull=True)
            | models.Q(termination_date__gte=service_date)
        ).values_list('contract_id', flat=True)

        match = qs.filter(
            contract_id__in=scoped_ids,
            network__network_id__in=self._network_ids_for(network_id),
        ).order_by('effective_start_date').last()
        return match.contract_id if match else None

    def _resolve_with_lob(self, qs, network_id, lob, service_date):
        """Contracts scoped to LOB only (no product FK)."""
        scoped_ids = ContractProductScope.objects.filter(
            lob_code=lob,
            product__isnull=True,
        ).filter(
            models.Q(effective_date__isnull=True)
            | models.Q(effective_date__lte=service_date)
        ).filter(
            models.Q(termination_date__isnull=True)
            | models.Q(termination_date__gte=service_date)
        ).values_list('contract_id', flat=True)

        legacy_scope_ids = ContractScope.objects.filter(
            line_of_business=lob,
        ).values_list('contract_id', flat=True)

        match = qs.filter(
            models.Q(contract_id__in=scoped_ids)
            | models.Q(contract_id__in=legacy_scope_ids)
            | models.Q(line_of_business=lob),
            network__network_id__in=self._network_ids_for(network_id),
        ).order_by('effective_start_date').last()
        return match.contract_id if match else None

    def _resolve_network_only(self, qs, network_id, service_date):
        """Contracts for this network regardless of LOB."""
        network_ids = self._network_ids_for(network_id)
        if not network_ids:
            return None
        match = qs.filter(
            network__network_id__in=network_ids,
        ).order_by('effective_start_date').last()
        return match.contract_id if match else None

    def _resolve_org_only(self, qs, service_date):
        """Fallback: any contract for this org."""
        match = qs.order_by('effective_start_date').last()
        return match.contract_id if match else None

    def _network_ids_for(self, network_id: int) -> list:
        """
        Given a products.Network.id, return the list of core.PayerNetwork.network_id
        strings that correspond to it (via Network.legacy_payer_network).
        """
        from products.models import Network

        try:
            net = Network.objects.get(id=network_id)
            if net.legacy_payer_network_id:
                return [net.legacy_payer_network_id]
        except Network.DoesNotExist:
            pass
        return []
