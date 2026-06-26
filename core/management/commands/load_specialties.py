"""
Load provider specialties from CSV (Phase 4).
Usage:
  python manage.py load_specialties --path path/to/specialties.csv
  python manage.py load_specialties --path path/to/specialties.csv --dry-run

CSV columns: specialty_code (required), description.
"""
import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import RefSpecialty


class Command(BaseCommand):
    help = 'Load provider specialties from CSV (Phase 4).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            type=str,
            required=True,
            help='Path to specialties CSV (columns: specialty_code, description)',
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
                specialty_code = (row.get('specialty_code') or '').strip()
                if not specialty_code:
                    continue
                description = (row.get('description') or '').strip() or None
                if dry_run:
                    self.stdout.write(f'Would upsert specialty: {specialty_code}')
                    count += 1
                    continue
                RefSpecialty.objects.update_or_create(
                    specialty_code=specialty_code,
                    defaults={'description': description},
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f'Specialty rows loaded/updated: {count}'))
