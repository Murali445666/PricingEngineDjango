"""Signals for audit logging (Phase 3 Segment 4)."""
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from core.models import PricingRule, RuleHistory


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
