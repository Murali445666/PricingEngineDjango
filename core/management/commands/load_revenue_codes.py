"""
Load revenue codes from CSV (Phase 4).
Usage:
  python manage.py load_revenue_codes --path path/to/revenue_codes.csv
  python manage.py load_revenue_codes --path path/to/revenue_codes.csv --dry-run

CSV columns: revenue_code (required), description, category.
"""
import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import RefRevenueCode


class Command(BaseCommand):
    help = 'Load revenue codes from CSV (Phase 4).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            type=str,
            required=True,
            help='Path to revenue codes CSV (columns: revenue_code, description, category)',
        )
        parser.add_argument('--dry-run', action='store_true', help='Print what would be done without writing to DB')

    def handle(self, *args, **options):
        path = options['path']
        dry_run = options.get('dry_run', False)
        p = Path(path)
        if not p.exists():
            self.stdout.write(self.style.ERROR(f'File not found: {path}'))
            return
        if dry_run:
            self.stdout.write('DRY RUN – no changes will be saved.')
        count = 0
        with open(p, newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        with transaction.atomic():
            for row in rows:
                revenue_code = (row.get('revenue_code') or '').strip()
                if not revenue_code:
                    continue
                description = (row.get('description') or '').strip() or None
                category = (row.get('category') or '').strip() or None
                if dry_run:
                    self.stdout.write(f'Would upsert revenue code: {revenue_code}')
                    count += 1
                    continue
                RefRevenueCode.objects.update_or_create(
                    revenue_code=revenue_code,
                    defaults={'description': description, 'category': category},
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f'Revenue code rows loaded/updated: {count}'))
