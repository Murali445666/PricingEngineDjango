"""
Load ICD-10-PCS procedure codes from CSV or from CMS tables XML (Phase 3).

CSV columns: procedure_code (required), description, section, body_system, year (required).

XML: CMS ICD-10-PCS tabular (e.g. icd10pcs_tables_2026.xml). Structure is pcsTable with
     axes (Section, Body System, Operation = pos 1,2,3; Body Part, Approach, Device, Qualifier = pos 4,5,6,7).
     Each valid combination of the 7 characters is emitted as one procedure code.

Usage:
  python manage.py load_icd10_pcs --path path/to/icd10_pcs.csv
  python manage.py load_icd10_pcs --path reference_data/icd10pcs_tables_2026.xml
  python manage.py load_icd10_pcs --path reference_data/icd10pcs_tables_2026.xml --dry-run
"""
import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import RefIcd10Pcs


def _int(s, default=None):
    if s is None or str(s).strip() == "":
        return default
    try:
        return int(str(s).strip())
    except Exception:
        return default


def _year_from_path(path: Path) -> int | None:
    """Infer year from filename, e.g. icd10pcs_tables_2026.xml -> 2026."""
    m = re.search(r"(\d{4})", path.name)
    return int(m.group(1)) if m else None


def _get_axis_labels(axis_el):
    """Return list of (code, text) for each <label code="X">text</label> in axis."""
    out = []
    for label in axis_el.findall("label"):
        code = label.get("code")
        text = (label.text or "").strip()
        if code is not None:
            out.append((str(code).strip(), text))
    return out


def _iter_codes_from_pcs_table(pcs_table_el):
    """
    Yield (procedure_code, description, section_title, body_system_title) for each
    valid 7-character PCS code in this table.
    Axes 1,2,3 (Section, Body System, Operation) are direct children of pcsTable;
    axes 4,5,6,7 (Body Part, Approach, Device, Qualifier) are inside each pcsRow.
    """
    # Table-level axes (pos 1, 2, 3) are direct children of pcsTable
    axes_by_pos = {}
    for axis in pcs_table_el.findall("axis"):
        pos = axis.get("pos")
        if pos is not None:
            axes_by_pos[int(pos)] = axis

    section_axis = axes_by_pos.get(1)
    body_axis = axes_by_pos.get(2)
    op_axis = axes_by_pos.get(3)
    if not all((section_axis, body_axis, op_axis)):
        return
    section_labels = _get_axis_labels(section_axis)
    body_labels = _get_axis_labels(body_axis)
    op_labels = _get_axis_labels(op_axis)
    if not section_labels or not body_labels or not op_labels:
        return
    section_code, section_title = section_labels[0]
    body_code, body_title = body_labels[0]
    op_code, op_title = op_labels[0]

    for pcs_row in pcs_table_el.findall("pcsRow"):
        # Axes 4,5,6,7 are inside this pcsRow, not at table level
        row_axes_by_pos = {}
        for axis in pcs_row.findall("axis"):
            pos = axis.get("pos")
            if pos is not None:
                row_axes_by_pos[int(pos)] = axis
        axes_4_7 = [
            _get_axis_labels(row_axes_by_pos[pos])
            for pos in (4, 5, 6, 7)
            if pos in row_axes_by_pos
        ]
        if len(axes_4_7) != 4:
            continue
        for bp_code, bp_text in axes_4_7[0]:
            for ap_code, ap_text in axes_4_7[1]:
                for dev_code, dev_text in axes_4_7[2]:
                    for qual_code, qual_text in axes_4_7[3]:
                        procedure_code = (
                            section_code + body_code + op_code + bp_code + ap_code + dev_code + qual_code
                        )
                        desc_parts = [op_title, bp_text, ap_text, dev_text, qual_text]
                        description = " - ".join(p for p in desc_parts if p)
                        if len(description) > 500:
                            description = description[:497] + "..."
                        yield procedure_code, description or None, section_title, body_title


def _read_rows_from_xml(path: Path, year: int | None):
    """Parse ICD-10-PCS tables XML; yield (procedure_code, description, section, body_system, year)."""
    tree = ET.parse(path)
    root = tree.getroot()
    effective_year = year
    version_el = root.find("version")
    if version_el is not None and (version_el.text or "").strip():
        try:
            effective_year = int((version_el.text or "").strip())
        except ValueError:
            pass
    if effective_year is None:
        effective_year = _year_from_path(path) or 2026
    for pcs_table in root.findall("pcsTable"):
        for procedure_code, description, section_title, body_title in _iter_codes_from_pcs_table(
            pcs_table
        ):
            yield procedure_code, description, section_title, body_title, effective_year


def _read_rows_from_csv(path: Path):
    """Read CSV; return list of dicts."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


class Command(BaseCommand):
    help = "Load ICD-10-PCS procedure codes from CSV or CMS tables XML."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            required=True,
            help="Path to ICD-10-PCS CSV or tables XML (e.g. icd10pcs_tables_2026.xml)",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Year (optional; XML uses <version> or filename, CSV uses column if present)",
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
            count = 0
            with transaction.atomic():
                for procedure_code, description, section_title, body_title, effective_year in _read_rows_from_xml(
                    path, year_arg
                ):
                    if not procedure_code or len(procedure_code) != 7:
                        continue
                    if section_title and len(section_title) > 20:
                        section_title = section_title[:20]
                    if body_title and len(body_title) > 50:
                        body_title = body_title[:50]
                    if dry_run:
                        self.stdout.write(f"Would upsert ICD-10-PCS: {procedure_code} year={effective_year}")
                        count += 1
                        continue
                    RefIcd10Pcs.objects.update_or_create(
                        procedure_code=procedure_code,
                        defaults={
                            "description": description,
                            "section": section_title or None,
                            "body_system": body_title or None,
                            "year": effective_year,
                        },
                    )
                    count += 1
            self.stdout.write(self.style.SUCCESS(f"ICD-10-PCS rows loaded/updated: {count} (from XML)"))
            return
        # CSV path
        rows = _read_rows_from_csv(path)
        count = 0
        with transaction.atomic():
            for row in rows:
                procedure_code = (row.get("procedure_code") or "").strip()
                if not procedure_code:
                    continue
                year = _int(row.get("year")) or year_arg
                if year is None:
                    if not dry_run:
                        self.stdout.write(
                            self.style.WARNING(f"Skipping {procedure_code}: year required")
                        )
                    continue
                description = (row.get("description") or "").strip() or None
                if description and len(description) > 500:
                    description = description[:500]
                section = (row.get("section") or "").strip() or None
                if section and len(section) > 20:
                    section = section[:20]
                body_system = (row.get("body_system") or "").strip() or None
                if body_system and len(body_system) > 50:
                    body_system = body_system[:50]
                if dry_run:
                    self.stdout.write(f"Would upsert ICD-10-PCS: {procedure_code} year={year}")
                    count += 1
                    continue
                RefIcd10Pcs.objects.update_or_create(
                    procedure_code=procedure_code,
                    defaults={
                        "description": description,
                        "section": section,
                        "body_system": body_system,
                        "year": year,
                    },
                )
                count += 1
        self.stdout.write(self.style.SUCCESS(f"ICD-10-PCS rows loaded/updated: {count}"))
