"""
§18 T1.1 — Amendment workflow: start amendment, publish, revert-to-draft, scheduled activation.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.models import ContractAmendment, ContractVersion, ContractVersionSnapshot, ProviderContract
from core.services.contract_cloning import clone_version_within_contract, _resolve_active_version
from core.services.contract_editing import contract_has_draft_version
from core.services.rule_lifecycle_service import RuleLifecycleService, _write_audit
from core.services.version_snapshot_service import (
    build_version_snapshot,
    diff_snapshots,
    save_version_snapshot,
)

User = get_user_model()


class AmendmentService:
    @classmethod
    def _ensure_no_draft_version(cls, contract: ProviderContract) -> None:
        if contract_has_draft_version(contract):
            raise ValidationError(
                f'Contract {contract.contract_id} already has a DRAFT version; '
                'only one editable DRAFT version is allowed at a time.'
            )

    @classmethod
    @transaction.atomic
    def start_amendment(
        cls,
        contract_id: int,
        *,
        amendment_number: str,
        effective_date: date,
        description: str,
        user=None,
    ) -> tuple[ContractAmendment, ContractVersion]:
        """
        Start an amendment on an ACTIVE contract: clone ACTIVE version → DRAFT, link amendment row.
        """
        try:
            contract = ProviderContract.objects.select_for_update().get(pk=contract_id)
        except ProviderContract.DoesNotExist as exc:
            raise ValidationError(f'Contract {contract_id} not found.') from exc

        if contract.status != 'ACTIVE':
            raise ValidationError(
                f'Amendments can only be started on ACTIVE contracts (current status: {contract.status}).'
            )

        cls._ensure_no_draft_version(contract)

        source_version = _resolve_active_version(contract)
        if source_version.status != ContractVersion.VersionStatus.ACTIVE:
            raise ValidationError(
                f'No ACTIVE version found on contract {contract_id} to amend.'
            )

        new_version, _summary = clone_version_within_contract(
            source_version,
            effective_start_date=effective_date,
            notes=f'Amendment {amendment_number}: {description}',
        )

        amendment = ContractAmendment.objects.create(
            contract=contract,
            version=new_version,
            amendment_number=amendment_number,
            effective_date=effective_date,
            description=description,
            status=ContractVersion.VersionStatus.DRAFT,
        )

        _write_audit(
            new_version,
            'AMENDMENT_STARTED',
            ContractVersion.VersionStatus.DRAFT,
            ContractVersion.VersionStatus.DRAFT,
            user=user,
            metadata={
                'amendment_id': amendment.id,
                'amendment_number': amendment_number,
                'source_version_id': source_version.version_id,
            },
        )
        return amendment, new_version

    @classmethod
    @transaction.atomic
    def apply_due_scheduled_activations(cls, contract_id: Optional[int] = None, user=None) -> list[int]:
        """
        Activate DRAFT versions whose scheduled_activation_date is today or in the past.
        Returns list of activated version_ids.
        """
        today = timezone.localdate()
        qs = ContractVersion.objects.select_for_update().filter(
            status=ContractVersion.VersionStatus.DRAFT,
            scheduled_activation_date__isnull=False,
            scheduled_activation_date__lte=today,
        )
        if contract_id is not None:
            qs = qs.filter(contract_id=contract_id)

        activated: list[int] = []
        for version in qs:
            version.scheduled_activation_date = None
            version.save(update_fields=['scheduled_activation_date'])
            RuleLifecycleService.activate_version(version.version_id, user=user)
            activated.append(version.version_id)
        return activated

    @classmethod
    @transaction.atomic
    def publish_version(cls, version_id: int, user=None) -> ContractVersion:
        """
        Publish a DRAFT version: validation must pass before calling.
        Writes snapshots, computes what_changed for amendments, handles future-dated activation.
        """
        cls.apply_due_scheduled_activations(user=user)

        version = ContractVersion.objects.select_for_update().select_related('contract').get(pk=version_id)
        if version.status != ContractVersion.VersionStatus.DRAFT:
            raise ValidationError(
                f'Cannot publish version {version_id}: status is {version.status} (must be DRAFT).'
            )

        contract = version.contract
        amendment = ContractAmendment.objects.filter(version=version).first()
        prior_active = (
            ContractVersion.objects.filter(
                contract=contract,
                status=ContractVersion.VersionStatus.ACTIVE,
            )
            .exclude(pk=version_id)
            .order_by('-version_number')
            .first()
        )

        prior_snapshot_data = None
        if prior_active is not None:
            prior_snap = save_version_snapshot(prior_active)
            prior_snapshot_data = prior_snap.snapshot

        new_snap_row = save_version_snapshot(version)
        new_snapshot_data = new_snap_row.snapshot

        if amendment is not None and prior_snapshot_data is not None:
            amendment.what_changed = diff_snapshots(prior_snapshot_data, new_snapshot_data)
            amendment.status = ContractVersion.VersionStatus.ACTIVE
            amendment.save(update_fields=['what_changed', 'status'])
        elif amendment is not None:
            amendment.what_changed = diff_snapshots(
                {'rules': [], 'roster': [], 'scope': [], 'version': {}},
                new_snapshot_data,
            )
            amendment.status = ContractVersion.VersionStatus.ACTIVE
            amendment.save(update_fields=['what_changed', 'status'])

        activation_date = amendment.effective_date if amendment else version.effective_start_date
        today = timezone.localdate()

        if activation_date > today:
            version.scheduled_activation_date = activation_date
            version.effective_start_date = activation_date
            version.save(update_fields=['scheduled_activation_date', 'effective_start_date'])
            _write_audit(
                version,
                'SCHEDULED',
                ContractVersion.VersionStatus.DRAFT,
                ContractVersion.VersionStatus.DRAFT,
                user=user,
                metadata={'scheduled_activation_date': activation_date.isoformat()},
            )
            return version

        version.scheduled_activation_date = None
        version.effective_start_date = activation_date
        version.save(update_fields=['scheduled_activation_date', 'effective_start_date'])

        activated = RuleLifecycleService.activate_version(version_id, user=user)

        if contract.status != 'ACTIVE':
            contract.status = 'ACTIVE'
            contract.save(update_fields=['status'])

        return activated

    @classmethod
    @transaction.atomic
    def revert_to_draft(cls, version_id: int, user=None) -> ContractVersion:
        """
        Move an ACTIVE version back to DRAFT for editing.
        Guard: only one DRAFT version per contract at a time.
        """
        version = ContractVersion.objects.select_for_update().select_related('contract').get(pk=version_id)
        if version.status != ContractVersion.VersionStatus.ACTIVE:
            raise ValidationError(
                f'Cannot revert version {version_id}: status is {version.status} (must be ACTIVE).'
            )

        contract = version.contract
        if contract_has_draft_version(contract):
            raise ValidationError(
                f'Contract {contract.contract_id} already has a DRAFT version; '
                'resolve or publish it before reverting another version.'
            )

        prev = version.status
        version.status = ContractVersion.VersionStatus.DRAFT
        version.scheduled_activation_date = None
        version.save(update_fields=['status', 'scheduled_activation_date'])

        amendment = ContractAmendment.objects.filter(version=version).first()
        if amendment is not None and amendment.status == ContractVersion.VersionStatus.ACTIVE:
            amendment.status = ContractVersion.VersionStatus.DRAFT
            amendment.save(update_fields=['status'])

        _write_audit(
            version,
            'REVERTED_TO_DRAFT',
            prev,
            ContractVersion.VersionStatus.DRAFT,
            user=user,
        )
        return version

    @classmethod
    @transaction.atomic
    def discard_draft(cls, version_id: int, user=None) -> dict[str, int]:
        """
        Permanently delete a DRAFT version, its linked amendment, and any draft snapshot.
        ACTIVE/SUPERSEDED/ARCHIVED versions cannot be discarded.
        """
        version = ContractVersion.objects.select_for_update().select_related('contract').get(pk=version_id)
        if version.status != ContractVersion.VersionStatus.DRAFT:
            raise ValidationError(
                f'Cannot discard version {version_id}: status is {version.status} (must be DRAFT).'
            )

        contract_id = version.contract_id
        version_number = version.version_number
        ContractAmendment.objects.filter(version=version).delete()
        ContractVersionSnapshot.objects.filter(version=version).delete()
        version.delete()

        return {
            'contract_id': contract_id,
            'version_id': version_id,
            'version_number': version_number,
        }
