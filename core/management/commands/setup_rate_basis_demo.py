"""Attach KEYSTONE-C-CARD rate basis + escalator demo (Gap A/B §16)."""
from django.core.management.base import BaseCommand

from core.demo.rate_basis_demo import attach_keystone_card_escalator, attach_keystone_card_rate_basis


class Command(BaseCommand):
    help = 'Create MPFS 2025 basis + 3%/yr escalator on KEYSTONE-C-CARD 99213 rule.'

    def handle(self, *args, **options):
        basis_result = attach_keystone_card_rate_basis(stdout=self.stdout)
        esc_result = attach_keystone_card_escalator(stdout=self.stdout)
        self.stdout.write(
            self.style.SUCCESS(
                f"Ready: contract_id={basis_result['contract_id']} rule_id={basis_result['rule_id']}"
            )
        )
        self.stdout.write(
            f"Escalator id={esc_result['escalator_id']} — "
            f"run: python manage.py materialize_rates --contract {basis_result['contract_id']} --year 2026"
        )
