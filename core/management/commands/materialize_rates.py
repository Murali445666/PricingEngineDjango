"""
Materialize ContractRateBasis rows to concrete engine-readable rates (Gap A/B §16).

Usage:
  python manage.py materialize_rates
  python manage.py materialize_rates --contract 213
  python manage.py materialize_rates --contract 213 --year 2026
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from core.services.rate_materialization import materialize_all, materialize_contract


class Command(BaseCommand):
    help = (
        'Materialize published-schedule rate bases (+ optional escalators) to '
        'PricingRule.flat_rate / ContractBaseRate (idempotent).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--contract',
            type=int,
            default=None,
            help='Limit to rules on this contract id',
        )
        parser.add_argument(
            '--year',
            type=int,
            default=None,
            help='Target materialization year (default: max(today, schedule year))',
        )

    def handle(self, *args, **options):
        contract_id = options.get('contract')
        target_year = options.get('year')
        year_label = target_year if target_year is not None else 'default'

        if contract_id is not None:
            results = materialize_contract(contract_id, target_year=target_year)
            self.stdout.write(f'Materializing contract_id={contract_id} year={year_label} …')
        else:
            results = materialize_all(target_year=target_year)
            self.stdout.write(f'Materializing all ContractRateBasis rows year={year_label} …')

        if not results:
            self.stdout.write(self.style.WARNING('No rules with ContractRateBasis found.'))
            return

        changed = 0
        skipped = 0
        for row in results:
            if row.get('skipped'):
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  SKIP rule {row['rule_id']} ({row.get('rule_name')}): {row.get('reason')}"
                    )
                )
                continue
            old = row.get('old')
            new = row.get('new')
            factor = row.get('escalator_factor', Decimal('1'))
            base_amt = row.get('base_amount')
            factor_note = f' escalator×{factor}' if factor and Decimal(str(factor)) != Decimal('1') else ''
            if old is not None and Decimal(str(old)) == Decimal(str(new)):
                self.stdout.write(
                    f"  rule {row['rule_id']} {row.get('code')} {row.get('field')}: "
                    f"unchanged ${new} ({row.get('basis')}, year={row.get('target_year')}{factor_note})"
                )
            else:
                changed += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  rule {row['rule_id']} {row.get('code')} {row.get('field')}: "
                        f"${old} -> ${new}  [{row.get('basis')}; base=${base_amt}; "
                        f"year={row.get('target_year')}{factor_note}]"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(f'\nDone: {changed} updated, {skipped} skipped, {len(results)} total.')
        )
