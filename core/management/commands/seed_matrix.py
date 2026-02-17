from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import (
    ProviderContract,
    ProviderOrganization,
    PayerNetwork,
    FeeSchedule,
    PricingRule,
    PricingRuleCondition,
)


class Command(BaseCommand):
    help = 'Seeds the database with Matrix Health test data'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write("Deleting old data...")
        ProviderContract.objects.all().delete()
        ProviderOrganization.objects.all().delete()
        PayerNetwork.objects.all().delete()
        FeeSchedule.objects.all().delete()
        # Note: We keep Reference Data (Codes/Modifiers) to avoid re-insertion issues
        # or you can wipe them too if you prefer clean slate.

        self.stdout.write("Creating Matrix Health Network...")
        
        # We can reuse the logic from the Test Utils by instantiating the class
        # (This is a quick hack to avoid duplicating code)
        # However, for a cleaner approach, let's copy the logic directly:
        
        # 1. Parents
        payer = ProviderOrganization.objects.create(organization_id="PAYER-MATRIX", name="Matrix Health", tax_id="99-9999999")
        provider = ProviderOrganization.objects.create(organization_id="PROV-GEN-HOSP", name="General Hospital", tax_id="11-1111111")
        network = PayerNetwork.objects.create(network_id="NET-COMMERCIAL", network_name="Matrix Commercial", payer_org=payer)

        # 2. Contract
        contract = ProviderContract.objects.create(
            contract_name="Matrix 2025", 
            legacy_contract_number="CONT-MATRIX-2026",
            status="ACTIVE", 
            effective_start_date="2025-01-01", 
            provider_org=provider, 
            network=network
        )

        # 3. Fee Schedule
        fs = FeeSchedule.objects.create(name="Matrix 2025 Standard", effective_date="2025-01-01")

        # 4. Rules (RBRVS example)
        r1 = PricingRule.objects.create(
            contract=contract,
            rule_name="RBRVS Standard",
            rule_type="BASE",
            specificity_score=10,
            methodology_code="RBRVS",
            base_fee_schedule=fs,
            multiplier=Decimal("1.50"),
        )
        PricingRuleCondition.objects.create(pricing_rule=r1, attribute_name="procedure_code", operator="EQ", attribute_value="99213")

        self.stdout.write(self.style.SUCCESS(f"Successfully seeded Contract: {contract.contract_name} (ID: {contract.pk})"))