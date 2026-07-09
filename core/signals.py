"""Signals for audit logging (Phase 3), Phase 5C snapshot invalidation, and Phase 7 specificity_score."""
from decimal import Decimal

from django.conf import settings
from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver

from core.models import (
    PricingRule,
    PricingRuleCondition,
    RuleHistory,
    ContractMethodology,
    ContractOutlierRule,
    ContractStopLossRule,
    ContractVersion,
    ContractScope,
    ContractProductScope,
    ContractProviderParticipation,
    ContractCapFloor,
)

# Marker for auto-attached baseline lesser-of-billed cap (LINE PCT_BILLED_CAP @ 100%, all codes).
# Use __isnull lookups — field=None does not match SQL NULL in Django filters.
_BASELINE_LESSER_OF_FILTER = {
    "scope": "LINE",
    "cap_type": "PCT_BILLED_CAP",
    "code_value__isnull": True,
    "conditions__isnull": True,
    "percentage": Decimal("100"),
    "priority": 0,
}


def ensure_default_lesser_of_billed_cap(version: ContractVersion) -> tuple[bool, ContractCapFloor | None]:
    """
    Idempotently attach the baseline LINE PCT_BILLED_CAP (100% of billed) to a version.
    Returns (created, cap_floor). Used by post_save signal and backfill command.
    """
    existing = ContractCapFloor.objects.filter(
        version=version,
        **_BASELINE_LESSER_OF_FILTER,
    ).first()
    if existing is not None:
        return False, existing

    cap = ContractCapFloor.objects.create(
        version=version,
        scope="LINE",
        cap_type="PCT_BILLED_CAP",
        percentage=Decimal("100"),
        value=None,
        code_value=None,
        conditions=None,
        priority=0,
        status=version.status,
        effective_start_date=version.effective_start_date,
        effective_end_date=version.effective_end_date,
    )
    return True, cap


@receiver(post_save, sender=ContractVersion)
def _attach_baseline_lesser_of_billed_cap(sender, instance, created, **kwargs):
    """Auto-create baseline LINE lesser-of-billed cap when a new ContractVersion is created."""
    if not created:
        return
    if not getattr(settings, "FEATURE_DEFAULT_LESSER_OF_BILLED", False):
        return
    ensure_default_lesser_of_billed_cap(instance)


@receiver(pre_save, sender=PricingRule)
def _stash_previous_rule_status(sender, instance, **kwargs):
    """Store previous status before save so post_save can log the change."""
    if instance.pk:
        try:
            old = PricingRule.objects.get(pk=instance.pk)
            instance._previous_status = old.status
        except PricingRule.DoesNotExist:
            instance._previous_status = ''
    else:
        instance._previous_status = ''


@receiver(post_save, sender=PricingRule)
def _log_rule_status_change(sender, instance, created, **kwargs):
    """Create a RuleHistory record when a rule is created or its status changes."""
    if created:
        RuleHistory.objects.create(
            pricing_rule=instance,
            previous_status='',
            new_status=instance.status,
            change_reason='Initial creation',
        )
        return
    previous = getattr(instance, '_previous_status', '')
    if previous != instance.status:
        RuleHistory.objects.create(
            pricing_rule=instance,
            previous_status=previous,
            new_status=instance.status,
            change_reason='',  # Optional: could be set by API/client later
        )


# Phase 7: Keep specificity_score in sync when conditions change (do not compute at query time)
@receiver(post_save, sender=PricingRuleCondition)
def _recalc_rule_score_on_condition_save(sender, instance, **kwargs):
    if instance.pricing_rule_id:
        instance.pricing_rule.calculate_score()


@receiver(post_delete, sender=PricingRuleCondition)
def _recalc_rule_score_on_condition_delete(sender, instance, **kwargs):
    if instance.pricing_rule_id:
        try:
            rule = PricingRule.objects.get(pk=instance.pricing_rule_id)
            rule.calculate_score()
        except PricingRule.DoesNotExist:
            pass


# Phase 5C: Invalidate materialized contract snapshot when contract config changes
@receiver(post_save, sender=PricingRule)
@receiver(post_delete, sender=PricingRule)
def _invalidate_contract_snapshot_on_rule_change(sender, instance, **kwargs):
    if getattr(instance, "contract_id", None):
        from core.services.contract_snapshot import invalidate_snapshot
        invalidate_snapshot(instance.contract_id)


@receiver(post_save, sender=ContractMethodology)
@receiver(post_delete, sender=ContractMethodology)
def _invalidate_contract_snapshot_on_methodology_change(sender, instance, **kwargs):
    if getattr(instance, "contract_id", None):
        from core.services.contract_snapshot import invalidate_snapshot
        invalidate_snapshot(instance.contract_id)


@receiver(post_save, sender=ContractOutlierRule)
@receiver(post_delete, sender=ContractOutlierRule)
def _invalidate_contract_snapshot_on_outlier_change(sender, instance, **kwargs):
    if getattr(instance, "contract_id", None):
        from core.services.contract_snapshot import invalidate_snapshot
        invalidate_snapshot(instance.contract_id)


@receiver(post_save, sender=ContractStopLossRule)
@receiver(post_delete, sender=ContractStopLossRule)
def _invalidate_contract_snapshot_on_stoploss_change(sender, instance, **kwargs):
    if getattr(instance, "contract_id", None):
        from core.services.contract_snapshot import invalidate_snapshot
        invalidate_snapshot(instance.contract_id)


@receiver(post_save, sender=ContractVersion)
@receiver(post_delete, sender=ContractVersion)
def _invalidate_contract_snapshot_on_version_change(sender, instance, **kwargs):
    if getattr(instance, "contract_id", None):
        from core.services.contract_snapshot import invalidate_snapshot
        invalidate_snapshot(instance.contract_id)


@receiver(post_save, sender=ContractScope)
def _sync_unified_from_contract_scope(sender, instance, **kwargs):
    from core.services.scope_unified_sync import sync_from_contract_scope
    sync_from_contract_scope(instance)


@receiver(post_delete, sender=ContractScope)
def _delete_unified_from_contract_scope(sender, instance, **kwargs):
    from core.services.scope_unified_sync import delete_unified_for_contract_scope
    delete_unified_for_contract_scope(instance.id)


@receiver(post_save, sender=ContractProductScope)
def _sync_unified_from_product_scope(sender, instance, **kwargs):
    from core.services.scope_unified_sync import sync_from_product_scope
    sync_from_product_scope(instance)


@receiver(post_delete, sender=ContractProductScope)
def _delete_unified_from_product_scope(sender, instance, **kwargs):
    from core.services.scope_unified_sync import delete_unified_for_product_scope
    delete_unified_for_product_scope(instance.id)


@receiver(post_save, sender=ContractScope)
@receiver(post_delete, sender=ContractScope)
def _invalidate_contract_snapshot_on_scope_change(sender, instance, **kwargs):
    if getattr(instance, "contract_id", None):
        from core.services.contract_snapshot import invalidate_snapshot
        invalidate_snapshot(instance.contract_id)


@receiver(post_save, sender=ContractProviderParticipation)
@receiver(post_delete, sender=ContractProviderParticipation)
def _invalidate_contract_snapshot_on_participation_change(sender, instance, **kwargs):
    if getattr(instance, "contract_id", None):
        from core.services.contract_snapshot import invalidate_snapshot
        invalidate_snapshot(instance.contract_id)
