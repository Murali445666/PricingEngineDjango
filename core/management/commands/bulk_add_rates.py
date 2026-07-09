"""
Bulk-add rate-basis rules for procedure codes (Gap D §16).

Usage:
  python manage.py bulk_add_rates --contract 214 --contract-version 47 --schedule 1 --percentage 120 \\
      --codes 99213,99214,99215,99203,99204
  python manage.py bulk_add_rates --contract 214 --contract-version 47 --schedule 1 --percentage 120 \\
      --csv rates.csv
"""
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.services.bulk_rates import bulk_add_rate_basis, parse_codes_csv, parse_codes_list


class Command(BaseCommand):
    help = 'Bulk-create PricingRules + ContractRateBasis rows and materialize rates.'

    def add_arguments(self, parser):
        parser.add_argument('--contract', type=int, required=True)
        parser.add_argument('--contract-version', type=int, required=True, dest='version_id')
        parser.add_argument('--schedule', type=int, required=True, help='PublishedFeeSchedule id')
        parser.add_argument('--percentage', type=str, required=True, help='e.g. 120 for 120%')
        parser.add_argument(
            '--codes',
            type=str,
            default=None,
            help='Comma-separated procedure codes',
        )
        parser.add_argument(
            '--csv',
            type=str,
            default=None,
            help='CSV file path: code[,methodology] per line',
        )
        parser.add_argument('--claim-type', type=str, default=None)
        parser.add_argument('--year', type=int, default=None, help='Materialization target year')
        parser.add_argument(
            '--methodology',
            type=str,
            default='FLAT_RATE',
            help='Default methodology when using --codes (default FLAT_RATE)',
        )

    def handle(self, *args, **options):
        codes_arg = options.get('codes')
        csv_path = options.get('csv')
        if not codes_arg and not csv_path:
            raise CommandError('Provide --codes or --csv')
        if codes_arg and csv_path:
            raise CommandError('Use only one of --codes or --csv')

        if csv_path:
            text = Path(csv_path).read_text(encoding='utf-8')
            specs = parse_codes_csv(text)
        else:
            specs = parse_codes_list(codes_arg.split(','), options['methodology'])

        if not specs:
            raise CommandError('No codes to process')

        try:
            result = bulk_add_rate_basis(
                options['contract'],
                options['version_id'],
                schedule_id=options['schedule'],
                percentage=Decimal(options['percentage']),
                codes=specs,
                claim_type=options.get('claim_type'),
                target_year=options.get('year'),
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            f'Bulk rate basis on contract {result.contract_id} version {result.version_id} '
            f'({len(specs)} code(s), {result.percentage}% of schedule {result.schedule_id})'
        )

        if result.created_rules:
            self.stdout.write(self.style.SUCCESS('\nRules created:'))
            for row in result.created_rules:
                self.stdout.write(
                    f"  rule {row['rule_id']} code={row['code']} methodology={row['methodology']}"
                )

        if result.updated_bases:
            self.stdout.write('\nRate bases attached/updated:')
            for row in result.updated_bases:
                flag = ' (new basis)' if row.get('created') else ''
                self.stdout.write(f"  rule {row['rule_id']} code={row['code']}{flag}")

        if result.materialized:
            self.stdout.write(self.style.SUCCESS('\nMaterialized rates:'))
            for row in result.materialized:
                self.stdout.write(
                    f"  rule {row['rule_id']} {row['code']}: ${row['flat_rate']} "
                    f"[{row.get('basis')}] year={row.get('target_year')}"
                )

        if result.skipped:
            self.stdout.write(self.style.WARNING('\nSkipped:'))
            for row in result.skipped:
                self.stdout.write(
                    f"  rule {row.get('rule_id')} code={row.get('code')}: {row.get('reason')}"
                )

        self.stdout.write(self.style.SUCCESS('\nDone.'))
