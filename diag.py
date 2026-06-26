import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from core.models import ProviderContract, PricingRule, ContractVersion

c = ProviderContract.objects.get(contract_name="DEMO-UC-B1")
print("CONTRACT:", c.contract_id, c.contract_name, "status=", c.status,
      "eff=", c.effective_start_date, "->", c.effective_end_date)
av = ContractVersion.objects.filter(contract=c)
for v in av:
    print("  VERSION", v.version_id, "status=", getattr(v,'status',None),
          "eff=", getattr(v,'effective_start_date',None), "->", getattr(v,'effective_end_date',None))

for r in PricingRule.objects.filter(contract=c):
    print("\nRULE", r.id, r.rule_name)
    for f in r._meta.fields:
        print(f"    {f.name} = {getattr(r, f.name)!r}")
    # conditions
    conds = r.conditions.all() if hasattr(r,'conditions') else []
    for cond in conds:
        print("    COND:", {f.name: getattr(cond,f.name) for f in cond._meta.fields})
