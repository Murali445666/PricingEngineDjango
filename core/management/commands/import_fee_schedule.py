"""

Import Exhibit C fee schedule CSV into PricingRule rows.



Usage:

  python manage.py import_fee_schedule \\

      --csv docs/Exhibit_C_Fee_Schedule.csv --contract <id> --contract-version <vid> --year 2025

"""

from pathlib import Path



from django.core.management.base import BaseCommand, CommandError



from core.services.fee_schedule_import import import_fee_schedule_from_csv





class Command(BaseCommand):

    help = 'Bulk-import PricingRule + PricingRuleCondition rows from Exhibit C CSV.'



    def add_arguments(self, parser):

        parser.add_argument('--csv', type=str, required=True, help='Path to Exhibit C CSV')

        parser.add_argument('--contract', type=int, required=True, help='ProviderContract id')

        parser.add_argument(

            '--contract-version',

            type=int,

            required=True,

            dest='version_id',

            help='ContractVersion id',

        )

        parser.add_argument(

            '--year',

            type=int,

            default=2025,

            help='Rate year column: 2025 → allowed_2025, 2026 → allowed_2026',

        )



    def handle(self, *args, **options):

        csv_path = Path(options['csv'])

        if not csv_path.exists():

            raise CommandError(f'CSV not found: {csv_path}')



        try:

            result = import_fee_schedule_from_csv(

                options['contract'],

                options['version_id'],

                csv_path,

                year=options['year'],

            )

        except Exception as exc:

            raise CommandError(str(exc)) from exc



        self.stdout.write(

            f'Imported fee schedule for contract {result.contract_id} '

            f'version {result.version_id} (year {result.year})'

        )

        self.stdout.write(self.style.SUCCESS(

            f'  rules created: {result.rules_created}'

        ))

        self.stdout.write(f'  rules updated: {result.rules_updated}')

        if result.rules_deleted:

            self.stdout.write(self.style.WARNING(

                f'  rules deleted (absent from CSV): {result.rules_deleted}'

            ))

        self.stdout.write(self.style.SUCCESS(

            f'  conditions created: {result.conditions_created}'

        ))

        self.stdout.write(self.style.SUCCESS(

            f'  rate bases created: {result.rate_bases_created}'

        ))

        self.stdout.write(f'  rate bases updated: {result.rate_bases_updated}')

        self.stdout.write(f'  rows processed: {result.rows_processed}')



        if result.rate_basis_skipped:

            self.stdout.write(

                f'  rate basis skipped (textual/non-numeric): {len(result.rate_basis_skipped)}'

            )



        if result.skipped:

            self.stdout.write(self.style.WARNING(f'  skipped: {len(result.skipped)}'))

            for row in result.skipped[:10]:

                self.stdout.write(f"    row {row.get('row')}: {row.get('reason')}")



        self.stdout.write(self.style.SUCCESS('\nDone.'))


