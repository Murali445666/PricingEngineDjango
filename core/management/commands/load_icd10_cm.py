"""
Load ICD-10-CM diagnosis codes from CSV or from CMS tabular XML (Phase 3).

CSV columns: diagnosis_code (required), description, billable_flag, effective_year (required).

XML: CMS ICD-10-CM tabular (e.g. icd10cm_tabular_2026.xml or icd10cm-tabular-April-2025.xml).
     Uses <version> for effective_year; recursively reads all <diag><name> and <diag><desc>.

Usage:
  python manage.py load_icd10_cm --path path/to/icd10_cm.csv
  python manage.py load_icd10_cm --path reference_data/icd10cm_tabular_2026.xml
  python manage.py load_icd10_cm --path reference_data/icd10cm_tabular_2026.xml --dry-run
"""
import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import RefIcd10Cm


def _int(s, default=None):
    if s is None or str(s).strip() == "":
        return default
    try:
        return int(str(s).strip())
    except Exception:
        return default


def _bool(s, default=True):
    if s is None or str(s).strip() == "":
        return default
    v = str(s).strip().upper()
    if v in ("1", "TRUE", "YES", "Y", "T"):
        return True
    if v in ("0", "FALSE", "NO", "N", "F"):
        return False
    return default


def _year_from_path(path: Path) -> int | None:
    """Infer effective year from filename, e.g. icd10cm_tabular_2026.xml -> 2026."""
    m = re.search(r"(\d{4})", path.name)
    return int(m.group(1)) if m else None


def _iter_diag_from_xml(root):
    """Yield (diagnosis_code, description) for every <diag> that has a <name>."""
    for diag in root.iter("diag"):
        name_el = diag.find("name")
        if name_el is None or not (name_el.text or "").strip():
            continue
        code = (name_el.text or "").strip()
        desc_el = diag.find("desc")
        desc = (desc_el.text or "").strip() if desc_el is not None else None
        yield code, desc


def _read_rows_from_xml(path: Path, effective_year: int | None):
    """Parse ICD-10-CM tabular XML; return list of (diagnosis_code, description); year from root <version> or argument."""
    tree = ET.parse(path)
    root = tree.getroot()
    year = effective_year
    version_el = root.find("version")
    if version_el is not None and (version_el.text or "").strip():
        try:
            year = int((version_el.text or "").strip())
        except ValueError:
            pass
    if year is None:
        year = _year_from_path(path) or 2025
    rows = []
    for code, desc in _iter_diag_from_xml(root):
        rows.append((code, desc, year))
    return rows


def _read_rows_from_csv(path: Path):
    """Read CSV; return list of dicts with diagnosis_code, description, billable_flag, effective_year."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


class Command(BaseCommand):
    help = "Load ICD-10-CM diagnosis codes from CSV or CMS tabular XML."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            required=True,
            help="Path to ICD-10-CM CSV or tabular XML (e.g. icd10cm_tabular_2026.xml)",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Effective year (optional; XML uses <version> or filename, CSV uses column if present)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be done without writing to DB",
        )

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.is_absolute():
            if not path.exists():
                alt = Path("reference_data") / path.name
                if alt.exists():
                    path = alt
        if not path.exists():
            self.stdout.write(self.style.ERROR(f"File not found: {path}"))
            return
        dry_run = options.get("dry_run", False)
        year_arg = options.get("year")
        if dry_run:
            self.stdout.write("DRY RUN – no changes will be saved.")
        suffix = path.suffix.lower()
        if suffix == ".xml":
            rows_xml = _read_rows_from_xml(path, year_arg)
            count = 0
            with transaction.atomic():
                for diagnosis_code, description, effective_year in rows_xml:
                    if not diagnosis_code:
                        continue
                    if description and len(description) > 500:
                        description = description[:500]
                    if dry_run:
                        self.stdout.write(f"Would upsert ICD-10-CM: {diagnosis_code} year={effective_year}")
                        count += 1
                        continue
                    RefIcd10Cm.objects.update_or_create(
                        diagnosis_code=diagnosis_code,
                        defaults={
                            "description": description or None,
                            "billable_flag": True,
                            "effective_year": effective_year,
                        },
                    )
                    count += 1
            self.stdout.write(self.style.SUCCESS(f"ICD-10-CM rows loaded/updated: {count} (from XML)"))
            return
        # CSV path
        rows = _read_rows_from_csv(path)
        count = 0
        with transaction.atomic():
            for row in rows:
                diagnosis_code = (row.get("diagnosis_code") or "").strip()
                if not diagnosis_code:
                    continue
                effective_year = _int(row.get("effective_year")) or year_arg
                if effective_year is None:
                    if not dry_run:
                        self.stdout.write(
                            self.style.WARNING(f"Skipping {diagnosis_code}: effective_year required")
                        )
                    continue
                description = (row.get("description") or "").strip() or None
                if description and len(description) > 500:
                    description = description[:500]
                billable_flag = _bool(row.get("billable_flag"), True)
                if dry_run:
                    self.stdout.write(f"Would upsert ICD-10-CM: {diagnosis_code} year={effective_year}")
                    count += 1
                    continue
                RefIcd10Cm.objects.update_or_create(
                    diagnosis_code=diagnosis_code,
                    defaults={
                        "description": description,
                        "billable_flag": billable_flag,
                        "effective_year": effective_year,
                    },
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"ICD-10-CM rows loaded/updated: {count}"))
