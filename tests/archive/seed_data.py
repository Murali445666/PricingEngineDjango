from django.core.management.base import BaseCommand
from core.models import ProviderOrganization, PayerNetwork, ProviderContract, PricingRule, PricingRuleCondition, RefProcedureCode, FeeSchedule, FeeScheduleRate, RefModifier
from datetime import date
from decimal import Decimal

class Command(BaseCommand):
    help = 'Seeds MySQL with Test Data (Compatible with V2 Schema)'

    def handle(self, *args, **kwargs):
        self.stdout.write("🌱 Seeding Data for V2 Schema...")

        # 1. Create Organization (Explicit String ID)
        org, _ = ProviderOrganization.objects.get_or_create(
            organization_id='ORG-001', # <--- NEW: Explicit ID
            defaults={'name': 'Allegheny Health Network', 'tax_id': '12-3456789'}
        )

        # 2. Create Network
        network, _ = PayerNetwork.objects.get_or_create(
            network_id='NET-001',      # <--- NEW: Explicit ID
            defaults={'network_name': 'Highmark Commercial', 'payer_org': org}
        )

        # 3. Create Contract
        contract, _ = ProviderContract.objects.get_or_create(
            legacy_contract_number='CONT-2026-A',
            defaults={
                'contract_name': 'Commercial 2026',
                'provider_org': org,
                'network': network,
                'status': 'ACTIVE',
                'effective_start_date': date(2026, 1, 1)
            }
        )

        # 4. Create Fee Schedule
        fs, _ = FeeSchedule.objects.get_or_create(
            name='Master FS 2026',
            defaults={'effective_date': date(2026, 1, 1), 'version': 1}
        )

        # 5. Create Ref Codes & Rates
        # Note: In V2, we must ensure the RefCode exists first!
        codes = [
            ('99213', 'CPT', '100.00'), 
            ('29881', 'CPT', '1000.00'),
            ('22551', 'CPT', '3333.33'),
            ('73030', 'CPT', '50.00'),
            ('29806', 'CPT', '500.00'),
            ('00100', 'CPT', '200.00'),
            ('+99100', 'CPT', '50.00')
        ]

        for code, ctype, rate in codes:
            # A. Ensure Reference Code Exists
            RefProcedureCode.objects.get_or_create(
                code_id=code,
                code_type=ctype,
                defaults={'description': 'Test Code'}
            )
            # B. Link Rate
            FeeScheduleRate.objects.get_or_create(
                fee_schedule=fs,
                code_id=code,
                defaults={'rate_amount': Decimal(rate)}
            )

        # 6. Create Base Pricing Rule
        rule, _ = PricingRule.objects.get_or_create(
            contract=contract,
            rule_name='Standard RBRVS',
            defaults={
                'rule_type': 'BASE',
                'methodology_code': 'RBRVS',
                'multiplier': Decimal('1.5000'),
                'base_fee_schedule': fs,
                'specificity_score': 10,
                'is_active': 1
            }
        )
        # Condition
        PricingRuleCondition.objects.get_or_create(
            pricing_rule=rule,
            attribute_name='code',
            operator='EQ',
            attribute_value='99213'
        )

        # 7. Create Modifiers (Required for Modifier Test)
        mods = ['26', 'TC', '50', '80']
        for m in mods:
            RefModifier.objects.get_or_create(
                modifier_code=m,
                defaults={'description': 'Test Mod', 'percentage_adjustment': 100.00}
            )

        self.stdout.write("✅ Seeding Complete.")