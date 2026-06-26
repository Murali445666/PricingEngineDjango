"""
Step 12b – Rule Lifecycle Service

Manages controlled lifecycle transitions for ContractVersion and version-scoped
rule objects (ContractCarveout, ContractCapFloor, ContractBlendingRule).

Allowed ContractVersion transitions:
  DRAFT      → ACTIVE      (activate_version)
  ACTIVE     → SUPERSEDED  (supersede_version — called automatically by activate_version)
  DRAFT      → ARCHIVED    (archive_version)
  SUPERSEDED → ARCHIVED    (archive_version)
  ACTIVE     → ARCHIVED    NOT allowed (must supersede first)

Allowed rule transitions (CarveOut / CapFloor / BlendingRule):
  DRAFT      → ACTIVE      (activate_rule)
  ACTIVE     → SUPERSEDED  (supersede_rule)
  any        → ARCHIVED    except ACTIVE (archive_rule)

Invariants:
  - All transitions are wrapped in transaction.atomic().
  - Every transition creates a ContractVersionAudit record.
  - This module MUST NOT import or call any pricing engine module.
"""
from __future__ import annotations

from typing import Optional, Union

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

User = get_user_model()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_audit(version, change_type: str, previous: str, new: str,
                 user=None, metadata: Optional[dict] = None):
    """Create an immutable ContractVersionAudit row."""
    from core.models import ContractVersionAudit  # local import avoids circular refs
    ContractVersionAudit.objects.create(
        version=version,
        changed_by=user,
        change_type=change_type,
        previous_status=previous,
        new_status=new,
        metadata=metadata or {},
    )


def _set_status(obj, new_status: str, *, save_fields=("status",)):
    obj.status = new_status
    obj.save(update_fields=save_fields)


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------

class RuleLifecycleService:
    """
    All public methods are class methods so callers do not need to instantiate.
    None of these methods may call ClaimOrchestrator, ClaimPricingService,
    PricingDataLoader, or any resolver/strategy module.
    """

    # ── Version lifecycle ────────────────────────────────────────────────────

    @classmethod
    @transaction.atomic
    def activate_version(cls, version_id: int, user=None) -> "ContractVersion":
        """
        Transition a DRAFT version to ACTIVE.

        Side-effect: any existing ACTIVE version for the same contract whose
        date range overlaps with the target version is automatically SUPERSEDED.

        Raises ValidationError if the version is not in DRAFT status.
        """
        from core.models import ContractVersion
        from core.services.validation_service import _ranges_overlap  # pure utility, not pricing

        version = ContractVersion.objects.select_for_update().get(pk=version_id)

        if version.status != ContractVersion.VersionStatus.DRAFT:
            raise ValidationError(
                f"Cannot activate version {version_id}: "
                f"current status is '{version.status}' (must be DRAFT)."
            )

        # Supersede any currently ACTIVE version for the same contract that overlaps
        overlapping = (
            ContractVersion.objects.select_for_update()
            .filter(contract=version.contract, status=ContractVersion.VersionStatus.ACTIVE)
            .exclude(pk=version_id)
        )
        for other in overlapping:
            if _ranges_overlap(
                version.effective_start_date, version.effective_end_date,
                other.effective_start_date, other.effective_end_date,
            ):
                prev = other.status
                _set_status(other, ContractVersion.VersionStatus.SUPERSEDED)
                _write_audit(
                    other, ContractVersionAudit_change_type("SUPERSEDED"),
                    prev, ContractVersion.VersionStatus.SUPERSEDED,
                    user=user,
                    metadata={"superseded_by_version": version_id},
                )

        prev = version.status
        _set_status(version, ContractVersion.VersionStatus.ACTIVE)
        _write_audit(
            version, "ACTIVATED", prev, ContractVersion.VersionStatus.ACTIVE, user=user
        )
        return version

    @classmethod
    @transaction.atomic
    def archive_version(cls, version_id: int, user=None) -> "ContractVersion":
        """
        Transition a DRAFT or SUPERSEDED version to ARCHIVED.
        ACTIVE versions cannot be archived directly — supersede first.

        Raises ValidationError if the version is ACTIVE.
        """
        from core.models import ContractVersion

        version = ContractVersion.objects.select_for_update().get(pk=version_id)

        if version.status == ContractVersion.VersionStatus.ACTIVE:
            raise ValidationError(
                f"Cannot archive version {version_id}: it is currently ACTIVE. "
                "Activate a replacement version first (which will auto-supersede this one)."
            )

        prev = version.status
        _set_status(version, ContractVersion.VersionStatus.ARCHIVED)
        _write_audit(version, "ARCHIVED", prev, ContractVersion.VersionStatus.ARCHIVED, user=user)
        return version

    # ── Rule-object lifecycle (CarveOut / CapFloor / BlendingRule) ───────────

    @classmethod
    @transaction.atomic
    def activate_rule(cls, rule_obj, user=None):
        """
        Transition a rule object (ContractCarveout / ContractCapFloor /
        ContractBlendingRule) from DRAFT → ACTIVE.

        The parent ContractVersion must itself be ACTIVE.
        Raises ValidationError otherwise.
        """
        from core.models import ContractVersion

        version = rule_obj.version
        if version is None or version.status != ContractVersion.VersionStatus.ACTIVE:
            raise ValidationError(
                f"Cannot activate rule {rule_obj!r}: "
                "parent ContractVersion must be ACTIVE."
            )

        if rule_obj.status != ContractVersion.VersionStatus.DRAFT:
            raise ValidationError(
                f"Cannot activate rule {rule_obj!r}: "
                f"current status is '{rule_obj.status}' (must be DRAFT)."
            )

        _set_status(rule_obj, ContractVersion.VersionStatus.ACTIVE)
        _write_audit(
            version, "ACTIVATED",
            ContractVersion.VersionStatus.DRAFT,
            ContractVersion.VersionStatus.ACTIVE,
            user=user,
            metadata={"rule_type": type(rule_obj).__name__, "rule_pk": rule_obj.pk},
        )
        return rule_obj

    @classmethod
    @transaction.atomic
    def supersede_rule(cls, rule_obj, user=None):
        """
        Transition a rule object from ACTIVE → SUPERSEDED.
        Raises ValidationError if not currently ACTIVE.
        """
        from core.models import ContractVersion

        if rule_obj.status != ContractVersion.VersionStatus.ACTIVE:
            raise ValidationError(
                f"Cannot supersede rule {rule_obj!r}: "
                f"current status is '{rule_obj.status}' (must be ACTIVE)."
            )

        version = rule_obj.version
        _set_status(rule_obj, ContractVersion.VersionStatus.SUPERSEDED)
        if version:
            _write_audit(
                version, "SUPERSEDED",
                ContractVersion.VersionStatus.ACTIVE,
                ContractVersion.VersionStatus.SUPERSEDED,
                user=user,
                metadata={"rule_type": type(rule_obj).__name__, "rule_pk": rule_obj.pk},
            )
        return rule_obj

    @classmethod
    @transaction.atomic
    def archive_rule(cls, rule_obj, user=None):
        """
        Transition a rule object to ARCHIVED.
        ACTIVE rules cannot be archived directly.
        """
        from core.models import ContractVersion

        if rule_obj.status == ContractVersion.VersionStatus.ACTIVE:
            raise ValidationError(
                f"Cannot archive rule {rule_obj!r}: it is ACTIVE. Supersede it first."
            )

        version = rule_obj.version
        prev = rule_obj.status
        _set_status(rule_obj, ContractVersion.VersionStatus.ARCHIVED)
        if version:
            _write_audit(
                version, "ARCHIVED", prev,
                ContractVersion.VersionStatus.ARCHIVED,
                user=user,
                metadata={"rule_type": type(rule_obj).__name__, "rule_pk": rule_obj.pk},
            )
        return rule_obj


# ---------------------------------------------------------------------------
# Tiny helper to keep _write_audit calls readable
# ---------------------------------------------------------------------------

def ContractVersionAudit_change_type(value: str) -> str:
    """Pass-through used to make the audit write calls self-documenting."""
    return value
