"""
Activate DRAFT contract versions whose scheduled_activation_date is today or in the past.

Schedule daily (cron / Windows Task Scheduler) so future-dated amendments go live on
their effective date without waiting for another publish.

Usage:
  python manage.py apply_scheduled_activations
  python manage.py apply_scheduled_activations --contract-id 217
"""
from django.core.management.base import BaseCommand

from core.services.amendment_service import AmendmentService


class Command(BaseCommand):
    help = (
        'Activate DRAFT versions with scheduled_activation_date <= today '
        '(supersedes overlapping ACTIVE versions).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--contract-id',
            type=int,
            default=None,
            help='Limit activation to a single contract.',
        )

    def handle(self, *args, **options):
        contract_id = options['contract_id']
        activated = AmendmentService.apply_due_scheduled_activations(contract_id=contract_id)
        if not activated:
            self.stdout.write('none due')
            return
        for version_id in activated:
            self.stdout.write(f'activated version_id={version_id}')
