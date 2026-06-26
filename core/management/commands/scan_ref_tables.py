"""
Scan all reference tables and print row counts.
Usage: python manage.py scan_ref_tables
"""
from django.core.management.base import BaseCommand
from django.apps import apps

# Ref* model names and optional short labels
REF_MODELS = [
    ("RefProcedureCode", "ref_procedure_codes", "Procedure codes (legacy)"),
    ("RefModifier", "ref_modifiers", "Modifiers"),
    ("RefGeoIndex", "ref_geo_indices", "GPCI / geographic indices"),
    ("RefCptHcpcsCode", "ref_cpt_hcpcs_codes", "CPT/HCPCS code master"),
    ("RefMpfsRvu", "ref_mpfs_rvu", "MPFS RVU by code/year"),
    ("RefDrg", "ref_drg", "DRG reference"),
    ("RefApc", "ref_apc", "APC reference"),
    ("RefIcd10Cm", "ref_icd10_cm", "ICD-10-CM diagnosis"),
    ("RefIcd10Pcs", "ref_icd10_pcs", "ICD-10-PCS procedure"),
    ("RefAspPricing", "ref_asp_pricing", "ASP drug pricing"),
    ("RefRevenueCode", "ref_revenue_codes", "Revenue codes"),
    ("RefSpecialty", "ref_specialties", "Specialties"),
]


class Command(BaseCommand):
    help = "Scan all reference tables and report row counts (empty vs populated)."

    def handle(self, *args, **options):
        self.stdout.write("Reference table row counts:")
        self.stdout.write("-" * 60)
        empty = []
        for model_name, table_name, label in REF_MODELS:
            try:
                model = apps.get_model("core", model_name)
                count = model.objects.count()
                status = "OK" if count > 0 else "EMPTY"
                self.stdout.write(f"  {table_name:<25} {count:>10}  {status:<6}  ({label})")
                if count == 0:
                    empty.append((table_name, label))
            except LookupError:
                self.stdout.write(self.style.WARNING(f"  {table_name:<25}  (model not found)"))
        self.stdout.write("-" * 60)
        if empty:
            self.stdout.write(self.style.WARNING(f"\nEmpty tables ({len(empty)}):"))
            for table_name, label in empty:
                self.stdout.write(f"  • {table_name} — {label}")
            self.stdout.write(
                "\nSee docs/RUNBOOK.md for load commands (load_cms_codes, load_pprrvu, load_gpci, load_drg, load_apc, load_asp_pricing, load_icd10_cm, load_revenue_codes, load_specialties)."
            )
        else:
            self.stdout.write(self.style.SUCCESS("\nAll reference tables have data."))
