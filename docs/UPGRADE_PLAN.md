# Matrix Platform — Architecture Alignment Upgrade Plan

**Document Status:** Active  
**Created:** June 2026  
**Scope:** Backend data model + API alignment with the System Architecture Design  
**UI Layer:** Deferred — will be planned separately  
**Engine:** `core/engine/` is frozen — no changes unless explicitly noted

---

## Current State Assessment

### What Exists Today

| Layer | Exists | Quality | Gap |
|---|---|---|---|
| Pricing engine (`core/engine/`) | ✅ Complete | Excellent | None — frozen |
| Contract + versioning lifecycle | ✅ Complete | Excellent | None |
| Rule engine (conditions, specificity, staged) | ✅ Complete | Excellent | None |
| Carve-outs, stop-loss, outlier, MPPR, blending | ✅ Complete | Good | None |
| Reference data (RVU, DRG, APC, ASP, ICD-10) | ✅ Complete | Good | None — loaders working |
| Contract validation + conflict detection | ✅ Complete | Good | None |
| `ProviderOrganization` model | ⚠️ Thin | Minimal | No NPI-type distinction, no hierarchy, no org_type |
| `PayerNetwork` model | ⚠️ Thin | Minimal | 3 fields; no network_type, no geography |
| `ClaimHeader` model | ⚠️ Partial | Partial | `npi` is a bare char field; no FK to individual provider; `member_id` is a bare char field (no FK); no facility FK |
| Provider (individual) domain | ❌ Missing | — | No `Provider` model |
| Facility domain | ❌ Missing | — | No `Facility` model |
| Provider affiliation | ❌ Missing | — | No `ProviderAffiliation` model |
| Network participation | ❌ Missing | — | No `ProviderNetworkParticipation` model |
| Payer (first-class) domain | ❌ Missing | — | Payer is embedded inside `PayerNetwork.payer_org` FK |
| Product / LOB / Plan domain | ❌ Missing | — | `line_of_business` is a bare `CharField` on 4 models; no `Product` model |
| Member / Enrollment domain | ❌ Missing | — | `member_id` is a `CharField(64)` on `ClaimHeader`; no `Member` model |
| Contract product scoping | ❌ Missing | — | No `ContractProductScope`; LOB is a bare CharField |
| Pricing Context Resolver | ❌ Missing | — | No `PricingContextResolver` service |
| Context-driven pricing APIs | ❌ Missing | — | No `/api/reprice-claim/`, no `/api/price-claim-by-provider/` |
| Debug prints in orchestrator | ⚠️ Present | Bad | 14 `print()` calls — must replace with `logging` |
| Frontend — pricing + simulation | ✅ Partial | Working | Needs context-aware endpoints when available |
| Frontend — contracts + rules | ✅ Partial | Working | Explorer, lifecycle, conflict detection |
| Frontend — provider/member/product UI | ❌ Missing | — | Out of scope for this plan — deferred |

### Key Specific Findings

**`ClaimHeader` gaps (line 1444 in `core/models.py`):**
- `npi = CharField(15)` — raw string, no FK to any provider entity
- `member_id = CharField(64)` — raw string, no FK to any member entity
- `provider_org` FK exists but points to `ProviderOrganization` (billing entity only)
- No `rendering_provider` FK, no `facility` FK, no `billing_npi` typed FK

**`ProviderOrganization` gaps (line 197 in `core/models.py`):**
- `npi` is a single CharField — no distinction between billing NPI (Type 2) and rendering NPI (Type 1)
- No `org_type` field (solo/group/IDS/health_system)
- No `parent_org` FK (no hierarchy support)
- No `tax_id` type validation, no EIN format enforcement

**`PayerNetwork` gaps (line 219 in `core/models.py`):**
- Only 4 data fields (`network_id`, `network_name`, `payer_org`, `line_of_business`)
- No `network_type` (HMO/PPO/EPO/ACO)
- The `payer_org` FK points to `ProviderOrganization` — conflating provider and payer organizations

**`ProviderContract` gaps (line 230 in `core/models.py`):**
- `line_of_business` is a bare `CharField(50)` — no FK to LOB entity, no validation
- No link to product — cannot do product-aware contract resolution
- `ContractScope` exists but LOB scoping is also a bare CharField

**`core/engine/orchestrator.py` — 14 live `print()` debug calls** must be replaced before any production use.

**`core/services/` is sparse:**  
Only 4 files: `condition_validation_service.py`, `contract_explorer_service.py`, `contract_snapshot.py`, `pricing_engine.py`. No context resolver, no provider lookup, no member lookup.

---

## Upgrade Strategy

### Principles
1. **Freeze the engine** — `core/engine/` is not touched except to add `logging` in place of `print()`
2. **Additive migrations only** — all new FK fields on existing models are `nullable=True`; no existing column is renamed or removed
3. **Test suite is the gate** — all 43 existing tests must pass after every stage
4. **New domains = new Django apps** — `providers/`, `members/`, `products/` each get their own app
5. **APIs follow data** — no new API endpoints are built until the underlying models exist
6. **Backward compatibility** — all existing API endpoints (`/api/price-line/`, `/api/price-claim/`, etc.) continue to work unchanged throughout

### Staged Plan Overview

```
Stage 0 (Immediate)  — Engine hygiene: print() → logging
Stage 1 (2–3 weeks)  — Provider domain: Provider, Facility, Affiliation, Network Participation
Stage 2 (2–3 weeks)  — Payer / Product / LOB / Network domain
Stage 3 (2–3 weeks)  — Member / Enrollment domain + ClaimHeader enrichment
Stage 4 (3–4 weeks)  — Pricing Context Resolver service + contract product scoping
Stage 5 (2–3 weeks)  — Context-driven pricing APIs
Stage 6 (ongoing)    — UI enhancements (separate plan)
```

---

## Stage 0 — Engine Hygiene (Immediate, < 1 Day)

**Goal:** Make the engine production-safe without changing any behavior.

### Tasks

| # | Task | File | Notes |
|---|---|---|---|
| 0.1 | Replace all `print()` with `import logging; logger = logging.getLogger(__name__)` | `core/engine/orchestrator.py` | 14 print calls; use `logger.debug()` for all of them |
| 0.2 | Add `LOGGING` config to `config/settings.py` | `config/settings.py` | Route `core.engine` logger to console at DEBUG level in dev; INFO in prod |
| 0.3 | Confirm all 43 tests still pass | `tests/` | Zero behavior change expected |

### Acceptance Criteria
- `grep -n "print(" core/engine/orchestrator.py` returns 0 results
- All existing tests pass
- Django dev server starts cleanly

---

## Stage 1 — Provider Domain (2–3 Weeks)

**Goal:** Add the individual provider, facility, affiliation, and network participation models. Zero changes to any existing model or API.

### New Django App: `providers/`

```
providers/
  __init__.py
  apps.py
  models.py
  admin.py
  serializers.py
  services.py        # ProviderLookupService
  migrations/
```

### Data Models

#### 1.1 `Provider` (Individual Clinician)

```python
class Provider(models.Model):
    """Individual rendering provider — NPI Type 1."""
    id = models.BigAutoField(primary_key=True)
    npi = models.CharField(max_length=15, unique=True, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    credential = models.CharField(max_length=50, null=True, blank=True)  # MD, DO, NP, PA
    primary_taxonomy = models.CharField(max_length=20, null=True, blank=True)  # NUCC code
    primary_specialty = models.ForeignKey(
        'core.RefSpecialty', on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField(max_length=20, default='ACTIVE')  # ACTIVE / INACTIVE
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'providers'
        indexes = [models.Index(fields=['npi'])]
```

#### 1.2 `Facility` (Place of Service Entity)

```python
class Facility(models.Model):
    """Physical facility — NPI Type 2 for places of service."""
    id = models.BigAutoField(primary_key=True)
    npi = models.CharField(max_length=15, unique=True, db_index=True)
    ccn = models.CharField(max_length=20, null=True, blank=True)  # CMS Certification Number
    name = models.CharField(max_length=255)
    facility_type = models.CharField(max_length=50)
    # HOSPITAL_INPATIENT / HOSPITAL_OUTPATIENT / ASC / SNF / FQHC / OFFICE / LAB / IMAGING
    place_of_service_codes = models.JSONField(default=list)  # list of CMS POS codes: ["21","22"]
    address_json = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'facilities'
```

#### 1.3 `ProviderOrganization` — Extend Existing (Additive Only)

Add to the **existing** `core.ProviderOrganization` model via migration:

```python
# New nullable fields — backward compatible
org_type = models.CharField(
    max_length=30, null=True, blank=True,
    choices=[('SOLO','Solo Practice'),('GROUP','Group Practice'),
             ('IDS','Integrated Delivery System'),('HEALTH_SYSTEM','Health System'),
             ('FACILITY','Facility/Hospital')]
)
parent_org = models.ForeignKey(
    'self', on_delete=models.SET_NULL, null=True, blank=True,
    db_column='parent_org_id', related_name='child_orgs'
)
npi_type = models.CharField(
    max_length=1, null=True, blank=True,
    choices=[('1','Type 1 - Individual'),('2','Type 2 - Organization')]
)
```

#### 1.4 `ProviderAffiliation` (Rendering → Billing Org, Dated)

```python
class ProviderAffiliation(models.Model):
    """Dated relationship: rendering provider works under billing org."""
    id = models.BigAutoField(primary_key=True)
    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE, related_name='affiliations'
    )
    organization = models.ForeignKey(
        'core.ProviderOrganization', on_delete=models.CASCADE, related_name='provider_affiliations'
    )
    role = models.CharField(
        max_length=30, default='EMPLOYEE',
        choices=[('EMPLOYEE','Employee'),('CONTRACTOR','Contractor'),
                 ('LOCUM','Locum Tenens'),('ADMITTING','Admitting'),('COVERING','Covering')]
    )
    effective_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'provider_affiliations'
        indexes = [
            models.Index(fields=['provider', 'organization', 'effective_date']),
        ]
```

#### 1.5 `ProviderNetworkParticipation` (Org or Individual → Network, Dated)

```python
class ProviderNetworkParticipation(models.Model):
    """Org or individual provider participation in a payer network on a date range."""
    id = models.BigAutoField(primary_key=True)
    organization = models.ForeignKey(
        'core.ProviderOrganization', on_delete=models.CASCADE,
        null=True, blank=True, related_name='network_participations'
    )
    provider = models.ForeignKey(
        Provider, on_delete=models.CASCADE,
        null=True, blank=True, related_name='network_participations'
    )
    # FK to PayerNetwork for now; will add FK to Network (products app) in Stage 2
    network = models.ForeignKey(
        'core.PayerNetwork', on_delete=models.CASCADE,
        related_name='provider_participations'
    )
    status = models.CharField(
        max_length=20, default='IN_NETWORK',
        choices=[('IN_NETWORK','In-Network'),('OUT_OF_NETWORK','Out-of-Network'),
                 ('TIER_1','Tier 1'),('TIER_2','Tier 2')]
    )
    effective_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    specialty_scope = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'provider_network_participations'
        indexes = [
            models.Index(fields=['organization', 'network', 'effective_date']),
            models.Index(fields=['provider', 'network', 'effective_date']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(organization__isnull=False) | models.Q(provider__isnull=False),
                name='participation_must_have_org_or_provider'
            )
        ]
```

#### 1.6 `FacilityNetworkParticipation`

```python
class FacilityNetworkParticipation(models.Model):
    """Facility participation in a payer network."""
    id = models.BigAutoField(primary_key=True)
    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name='network_participations')
    network = models.ForeignKey('core.PayerNetwork', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='IN_NETWORK')
    effective_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'facility_network_participations'
        indexes = [
            models.Index(fields=['facility', 'network', 'effective_date']),
        ]
```

### Service: `ProviderLookupService`

```python
# providers/services.py
class ProviderLookupService:
    def resolve_org_by_billing_npi(self, npi: str) -> ProviderOrganization | None: ...
    def resolve_provider_by_rendering_npi(self, npi: str) -> Provider | None: ...
    def resolve_facility_by_npi(self, npi: str) -> Facility | None: ...
    def check_affiliation(self, provider_id: int, org_id: str, service_date: date) -> bool: ...
    def check_org_network_participation(
        self, org_id: str, network_id: str, service_date: date
    ) -> str | None:  # returns status or None if not found
        ...
```

### Admin Registration

Register all new models in `providers/admin.py`. Include:
- `ProviderAdmin` with search by NPI, last name, specialty
- `FacilityAdmin` with search by NPI, CCN, facility type
- `ProviderAffiliationAdmin` with inline on Provider
- `ProviderNetworkParticipationAdmin` with date-range validation

### Management Commands

```
providers/management/commands/
  load_providers.py      # bulk load from NPI CSV
  load_facilities.py     # bulk load facilities from NPI CSV
```

### Stage 1 Acceptance Criteria
- [ ] `python manage.py migrate` runs cleanly
- [ ] All 43 existing tests pass
- [ ] `ProviderOrganization` existing FKs still work (backwards compatible)
- [ ] Django admin shows Provider, Facility, ProviderAffiliation, ProviderNetworkParticipation
- [ ] `ProviderLookupService.check_affiliation()` returns correct result for seeded test data
- [ ] No changes to `core/engine/` or `core/api/`

---

## Stage 2 — Payer / Product / LOB / Network Domain (2–3 Weeks)

**Goal:** Add first-class Payer, LOB, Product, and Network models. Extend `PayerNetwork` with proper typing. Wire `ProviderNetworkParticipation` to the new `Network` model.

### New Django App: `products/`

```
products/
  __init__.py
  apps.py
  models.py
  admin.py
  serializers.py
  services.py        # NetworkLookupService
  migrations/
```

### Data Models

#### 2.1 `PayerOrganization` (First-Class Payer Entity)

```python
class PayerOrganization(models.Model):
    """A payer: insurance company, TPA, or government payer."""
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    payer_id = models.CharField(max_length=50, unique=True, db_index=True)  # EDI payer ID
    payer_type = models.CharField(
        max_length=30,
        choices=[('COMMERCIAL','Commercial'),('MEDICARE_ADVANTAGE','Medicare Advantage'),
                 ('MEDICAID','Medicaid'),('SELF_FUNDED','Self-Funded'),('TPA','TPA'),
                 ('CMS','CMS/Medicare FFS')]
    )
    parent_name = models.CharField(max_length=255, null=True, blank=True)  # e.g., "BCBS National"
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payer_organizations'
```

#### 2.2 `LineOfBusiness`

```python
class LineOfBusiness(models.Model):
    """Top-level segment: Commercial, MA, Medicaid, Exchange, Self-Funded."""
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(
        max_length=30, unique=True,
        choices=[
            ('COMMERCIAL','Commercial'),
            ('MEDICARE_ADVANTAGE','Medicare Advantage'),
            ('MEDICAID','Medicaid'),
            ('EXCHANGE','Exchange / ACA'),
            ('SELF_FUNDED','Self-Funded'),
            ('MEDICARE_FFS','Medicare Fee-for-Service'),
        ]
    )
    name = models.CharField(max_length=100)

    class Meta:
        db_table = 'lines_of_business'
        verbose_name_plural = 'Lines of Business'
```

#### 2.3 `Product`

```python
class Product(models.Model):
    """A named insurance product offered by a payer under a specific LOB."""
    id = models.BigAutoField(primary_key=True)
    payer = models.ForeignKey(PayerOrganization, on_delete=models.CASCADE, related_name='products')
    lob = models.ForeignKey(LineOfBusiness, on_delete=models.PROTECT, related_name='products')
    name = models.CharField(max_length=255)
    product_code = models.CharField(max_length=50, null=True, blank=True)
    effective_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        indexes = [models.Index(fields=['payer', 'effective_date'])]
```

#### 2.4 `Network` (Replaces/Wraps `PayerNetwork`)

```python
class Network(models.Model):
    """
    First-class network model. Linked from existing PayerNetwork via legacy_payer_network FK.
    ProviderNetworkParticipation migrates from PayerNetwork FK to Network FK in this stage.
    """
    id = models.BigAutoField(primary_key=True)
    payer = models.ForeignKey(PayerOrganization, on_delete=models.CASCADE, related_name='networks')
    name = models.CharField(max_length=255)
    network_code = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    network_type = models.CharField(
        max_length=20,
        choices=[('PPO','PPO'),('HMO','HMO'),('EPO','EPO'),('POS','POS'),
                 ('ACO','ACO'),('NARROW','Narrow'),('TIERED','Tiered')]
    )
    # Migration bridge: link to legacy PayerNetwork for backward compat
    legacy_payer_network = models.OneToOneField(
        'core.PayerNetwork', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='network_record'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'networks'
```

#### 2.5 `ProductNetworkConfig`

```python
class ProductNetworkConfig(models.Model):
    """Which network a product uses for a given claim type and date range."""
    id = models.BigAutoField(primary_key=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='network_configs')
    network = models.ForeignKey(Network, on_delete=models.CASCADE, related_name='product_configs')
    claim_type = models.CharField(
        max_length=30, default='ALL',
        choices=[('ALL','All'),('PROFESSIONAL','Professional'),
                 ('INSTITUTIONAL','Institutional'),('BEHAVIORAL_HEALTH','Behavioral Health')]
    )
    effective_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'product_network_configs'
        indexes = [models.Index(fields=['product', 'claim_type', 'effective_date'])]
```

#### 2.6 Migrate `ProviderNetworkParticipation.network` FK

In `Stage 2` migration: add a `network_new` FK to `products.Network` on `ProviderNetworkParticipation` (nullable). Existing `network` FK to `core.PayerNetwork` remains. Once `Network` is populated, the resolver uses `network_new`; legacy `network` stays for backward compat.

#### 2.7 `ContractProductScope` — Extend Contract Domain

Add to `core/models.py` (stays in `core` since it extends `ProviderContract`):

```python
class ContractProductScope(models.Model):
    """
    Links a contract to the LOB / Product(s) it applies to.
    If no record exists for a contract, the contract is treated as LOB-agnostic (matches all).
    """
    id = models.BigAutoField(primary_key=True)
    contract = models.ForeignKey(
        ProviderContract, on_delete=models.CASCADE, related_name='product_scopes'
    )
    lob_code = models.CharField(
        max_length=30, null=True, blank=True,
        help_text="If set, restricts this contract to a line of business."
    )
    product = models.ForeignKey(
        'products.Product', on_delete=models.SET_NULL, null=True, blank=True,
        help_text="If set, further restricts to a specific product."
    )
    effective_date = models.DateField(null=True, blank=True)
    termination_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contract_product_scopes'
```

### `PayerNetwork` — Extend Existing (Additive)

Add to existing `core.PayerNetwork` model:

```python
network_type = models.CharField(max_length=20, null=True, blank=True)  # PPO/HMO/EPO etc.
```

### Service: `NetworkLookupService`

```python
# products/services.py
class NetworkLookupService:
    def resolve_network(
        self, product_id: int, claim_type: str, service_date: date
    ) -> Network | None: ...

    def check_org_participation(
        self, org_id: str, network_id: int, service_date: date
    ) -> str | None:  # returns status string or None
        ...
```

### Stage 2 Acceptance Criteria
- [ ] `python manage.py migrate` runs cleanly
- [ ] All 43 existing tests pass
- [ ] `PayerNetwork` existing FKs on `ProviderContract` unchanged
- [ ] `ContractProductScope` can be created for any contract without breaking existing pricing
- [ ] `NetworkLookupService.resolve_network()` returns correct network for a test product + date
- [ ] Admin shows PayerOrganization, LineOfBusiness, Product, Network, ProductNetworkConfig, ContractProductScope

---

## Stage 3 — Member / Enrollment + ClaimHeader Enrichment (2–3 Weeks)

**Goal:** Add member and enrollment domain. Enrich `ClaimHeader` with typed FK fields for rendering provider, facility, and member.

### New Django App: `members/`

```
members/
  __init__.py
  apps.py
  models.py
  admin.py
  serializers.py
  services.py        # MemberLookupService
  migrations/
```

### Data Models

#### 3.1 `Member`

```python
class Member(models.Model):
    """Individual covered by an insurance product."""
    id = models.BigAutoField(primary_key=True)
    member_id = models.CharField(max_length=64, unique=True, db_index=True)
    first_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    zip_code = models.CharField(max_length=10, null=True, blank=True)  # for GPCI locality
    subscriber_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    relationship_to_subscriber = models.CharField(
        max_length=20, default='SELF',
        choices=[('SELF','Self'),('SPOUSE','Spouse'),('DEPENDENT','Dependent'),('OTHER','Other')]
    )
    # Future hook — do not enforce now
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'members'
```

#### 3.2 `Enrollment`

```python
class Enrollment(models.Model):
    """Member's enrollment in a specific Product on a date range."""
    id = models.BigAutoField(primary_key=True)
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='enrollments')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='enrollments')
    effective_date = models.DateField(db_index=True)
    termination_date = models.DateField(null=True, blank=True)
    # Future hooks — do not enforce now
    # benefit_plan = FK(BenefitPlan, null=True)
    # eligibility_status = CharField(null=True)
    # cob_order = IntegerField(null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'enrollments'
        indexes = [
            models.Index(fields=['member', 'effective_date']),
            models.Index(fields=['member', 'termination_date']),
        ]
```

### Service: `MemberLookupService`

```python
# members/services.py
class MemberLookupService:
    def resolve_enrollment(
        self, member_id: str, service_date: date
    ) -> Enrollment | None:
        """Return active enrollment on service_date or None."""
        ...

    def get_product(self, member_id: str, service_date: date) -> Product | None: ...
    def get_lob(self, member_id: str, service_date: date) -> str | None: ...
    def get_locality_zip(self, member_id: str) -> str | None: ...
```

### 3.3 `ClaimHeader` — Extend Existing (Additive, All Nullable)

Add via migration to `core.ClaimHeader`:

```python
# All nullable — existing rows and existing tests are unaffected
rendering_provider = models.ForeignKey(
    'providers.Provider', on_delete=models.SET_NULL,
    null=True, blank=True, db_column='rendering_provider_id', related_name='claim_headers'
)
facility = models.ForeignKey(
    'providers.Facility', on_delete=models.SET_NULL,
    null=True, blank=True, db_column='facility_id', related_name='claim_headers'
)
member = models.ForeignKey(
    'members.Member', on_delete=models.SET_NULL,
    null=True, blank=True, db_column='member_fk_id', related_name='claim_headers'
)
billing_npi = models.CharField(max_length=15, null=True, blank=True)
```

> **Note on existing `npi` field:** The existing `npi = CharField(15)` on `ClaimHeader` is ambiguous (billing or rendering?). Add `billing_npi` as the typed replacement. Deprecate `npi` in a later cleanup migration but do not remove it now — existing tests reference it.

### Stage 3 Acceptance Criteria
- [ ] `python manage.py migrate` runs cleanly
- [ ] All 43 existing tests pass — `ClaimHeader` FK extensions are nullable, no existing test fails
- [ ] `MemberLookupService.resolve_enrollment()` returns correct Enrollment for test data
- [ ] `ClaimHeader` can be created with `rendering_provider`, `facility`, `member` FKs populated
- [ ] `ClaimHeader` can still be created without any of those FKs (backward compat)
- [ ] Admin shows Member, Enrollment with inline enrollments on Member

---

## Stage 4 — Pricing Context Resolver (3–4 Weeks)

**Goal:** Build the `PricingContextResolver` service and the `ClaimPricingContext` DTO. No new API endpoints yet — the resolver is tested via unit tests and an internal debug endpoint only.

### 4.1 Add `ClaimPricingContext` DTO to Engine Types

Add to `core/engine/types.py` (additive — existing types unchanged):

```python
@dataclass(frozen=True)
class ProviderPricingContext:
    billing_org_id: str | None
    billing_org_tax_id: str | None
    rendering_provider_id: int | None
    rendering_provider_specialty: str | None
    facility_id: int | None
    facility_type: str | None
    place_of_service: str | None
    network_status: str | None        # IN_NETWORK / OUT_OF_NETWORK / UNKNOWN
    network_tier: str | None
    affiliation_verified: bool

@dataclass(frozen=True)
class MemberPricingContext:
    member_id: str | None
    product_id: int | None
    lob: str | None
    network_id: int | None
    locality_zip: str | None
    enrollment_id: int | None

@dataclass(frozen=True)
class ClaimPricingContext:
    resolution_mode: str              # DIRECT / RESOLVED / OON
    contract_id: int
    version_id: int | None
    provider: ProviderPricingContext
    member: MemberPricingContext
    service_date: date
    pricing_date: date
    claim_type: str
    lines: list                       # list[ClaimLineInput] — existing type
    simulation_mode: bool = False
    draft_rule: dict | None = None
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    requested_by: str | None = None
```

### 4.2 New Service: `core/services/pricing_context_resolver.py`

```
core/services/
  pricing_context_resolver.py      # PricingContextResolver (main)
  contract_resolver.py             # ContractResolver (extracted from loader.py)
```

#### `ContractResolver`

Extracted from `loader.py`'s current `resolve_contract_for_claim()` and enhanced:

```python
class ContractResolver:
    def resolve(
        self,
        org_id: str,
        network_id: int | None,     # new Network.id (None falls back to legacy)
        lob: str | None,
        service_date: date
    ) -> int | None:
        """
        Returns contract_id of the best-matching ProviderContract.
        Resolution order (most to least specific):
          1. org + network + lob + product scope match
          2. org + network + lob match (no product scope on contract)
          3. org + network match (no LOB)
          4. org match only (no network scoping)
        Returns None if no contract found (caller triggers OON path).
        """
```

#### `PricingContextResolver`

```python
class PricingContextResolver:
    def __init__(
        self,
        provider_svc: ProviderLookupService,
        member_svc: MemberLookupService,
        network_svc: NetworkLookupService,
        contract_resolver: ContractResolver,
    ): ...

    def resolve(self, raw: RawClaimInput) -> ClaimPricingContext:
        """
        1. resolve org from billing_npi
        2. resolve rendering provider from rendering_npi
        3. resolve enrollment from member_id + service_date
        4. resolve network from product + claim_type + service_date
        5. check org network participation on service_date
        6. resolve contract from org + network + lob + service_date
        7. assemble and return frozen ClaimPricingContext
        """

    def resolve_provider_only(self, raw: RawClaimInput) -> ClaimPricingContext:
        """Resolution without member context — used for provider-side pricing."""
```

#### `RawClaimInput` DTO (request input)

```python
@dataclass
class RawClaimInput:
    billing_npi: str | None = None
    rendering_npi: str | None = None
    member_id: str | None = None
    service_date: date = None
    pricing_date: date | None = None
    claim_type: str = 'professional'
    lines: list = field(default_factory=list)
    # Optional overrides
    override_contract_id: int | None = None   # bypass resolution
    override_network_id: int | None = None
```

### 4.3 Extend `ClaimPricingService`

Add one new method to `core/engine/service.py` (existing methods unchanged):

```python
def price_claim_from_context(self, ctx: ClaimPricingContext) -> ClaimPricingResult:
    """New entry point — consumes fully-resolved context from PricingContextResolver."""
    return self.price_claim(
        contract_id=ctx.contract_id,
        lines=ctx.lines,
        service_date=ctx.service_date,
        claim_type=ctx.claim_type,
        product_id=ctx.member.product_id,
        network_id=ctx.member.network_id,
        network_tier=ctx.provider.network_tier,
        version_id=ctx.version_id,
    )
```

### 4.4 Debug Endpoint (Internal Only)

Add one endpoint to `core/api/urls.py` for testing the resolver without running pricing:

```
GET /api/resolve-context/
  ?billing_npi=&rendering_npi=&member_id=&service_date=&claim_type=
```

Returns the resolved `ClaimPricingContext` as JSON — no pricing executed. Used for development validation only.

### Stage 4 Acceptance Criteria
- [ ] All 43 existing tests pass
- [ ] `PricingContextResolver.resolve()` correctly resolves contract for a seeded test case with member + provider + network
- [ ] `PricingContextResolver.resolve_provider_only()` works without member context
- [ ] `ContractResolver` produces same results as the current `resolve_contract_for_claim()` for direct `contract_id` calls (regression test)
- [ ] `ClaimPricingService.price_claim_from_context()` produces identical output to `price_claim()` when given equivalent inputs
- [ ] `/api/resolve-context/` returns correct JSON for a known test case
- [ ] OON path: when no in-network contract found, resolver raises `ContractResolutionError` with `OON` status (engine handles gracefully)

---

## Stage 5 — Context-Driven Pricing APIs (2–3 Weeks)

**Goal:** Expose the resolver via new API endpoints aligned with the use cases. All existing endpoints remain unchanged.

### New Endpoints

#### 5.1 `POST /api/reprice-claim/`
**Use case:** Payer repricing team — submit a claim with member + provider context; system resolves the contract and returns pricing.

```
Request:
{
  "billing_npi": "1234567890",
  "rendering_npi": "0987654321",
  "member_id": "M-00112",
  "service_date": "2025-06-01",
  "claim_type": "professional",
  "lines": [
    { "procedure_code": "99213", "billed_amount": 250.00, "units": 1, "modifiers": [] }
  ]
}

Response: ClaimPricingResult + resolution_context {
  "contract_id": 42,
  "contract_name": "BluePPO Commercial 2025",
  "network_status": "IN_NETWORK",
  "lob": "COMMERCIAL",
  "member_id": "M-00112",
  "product_name": "BlueSelect PPO",
  "resolution_mode": "RESOLVED",
  "allowed_amount": 95.40,
  "lines": [...]
}
```

#### 5.2 `POST /api/price-claim-by-provider/`
**Use case:** Provider reimbursement analyst — provider-side pricing without member context.

```
Request:
{
  "billing_npi": "1234567890",
  "rendering_npi": "0987654321",
  "service_date": "2025-06-01",
  "claim_type": "professional",
  "lines": [...]
}

Response: Same shape as reprice-claim, resolution_mode = "RESOLVED" or "NO_CONTRACT"
```

#### 5.3 `POST /api/reprice-claim-batch/`
**Use case:** Batch repricing run — multiple claims, context resolved per claim.

```
Request:
{
  "claims": [
    {
      "claim_ref": "CLM-001",
      "billing_npi": "...", "member_id": "...", "service_date": "...",
      "lines": [...]
    },
    ...
  ],
  "max_claims": 500
}

Response: {
  "total": 3,
  "resolved": 3,
  "failed": 0,
  "results": [{ "claim_ref": "CLM-001", "contract_id": 42, "allowed_amount": 95.40, ... }]
}
```

#### 5.4 `GET /api/resolve-context/` (Already added in Stage 4)
**Use case:** Analyst debugging contract resolution.
Promoted from internal-only to documented endpoint.

#### 5.5 `GET /api/providers/`
**Use case:** Look up provider by NPI.

```
GET /api/providers/?npi=1234567890
GET /api/providers/?name=Smith&specialty=Internal+Medicine
Response: { id, npi, first_name, last_name, specialty, status, affiliations[] }
```

#### 5.6 `GET /api/providers/<id>/network-status/`
**Use case:** Check provider network participation.

```
GET /api/providers/12/network-status/?network_id=5&service_date=2025-06-01
Response: { status: "IN_NETWORK", tier: null, effective_date: "2024-01-01" }
```

#### 5.7 `GET /api/members/<member_id>/enrollment/`
**Use case:** Look up member enrollment on a date.

```
GET /api/members/M-00112/enrollment/?service_date=2025-06-01
Response: { member_id, product_id, product_name, lob, network_id, network_name, effective_date }
```

#### 5.8 `GET /api/products/`
**Use case:** Look up products / LOBs for contract scoping UI.

```
GET /api/products/?payer_id=5
Response: [{ id, name, lob, payer, network_configs[] }]
```

### Serializers Required

| Serializer | Location |
|---|---|
| `RawClaimInputSerializer` | `core/api/serializers.py` |
| `RepricingResultSerializer` | `core/api/serializers.py` (extends `ClaimPricingResultSerializer`) |
| `ProviderSerializer` | `providers/` app |
| `ProviderNetworkParticipationSerializer` | `providers/` app |
| `MemberSerializer` | `members/` app |
| `EnrollmentSerializer` | `members/` app |
| `ProductSerializer` | `products/` app |
| `NetworkSerializer` | `products/` app |

### Stage 5 Acceptance Criteria
- [ ] All 43 existing tests pass (no regressions)
- [ ] `POST /api/reprice-claim/` returns correct pricing + resolution context for end-to-end test with seeded member, provider, product, network, and contract
- [ ] `POST /api/price-claim-by-provider/` works without member context
- [ ] `POST /api/reprice-claim-batch/` handles 10 claims and returns correct results
- [ ] `GET /api/providers/?npi=` returns provider record
- [ ] `GET /api/members/<id>/enrollment/?service_date=` returns correct enrollment
- [ ] All new endpoints documented in a Postman collection or API doc
- [ ] OON case: `POST /api/reprice-claim/` with OON provider returns `{ "network_status": "OUT_OF_NETWORK", "contract_id": null, "status": "NO_CONTRACT" }`

---

## Stage 6 — UI Enhancements (Separate Plan, TBD)

UI work is deferred to a separate planning document. The following is a placeholder list of what will be needed once the backend stages are complete.

### Anticipated UI Work (Not Planned Here)
- Provider lookup and network status page (uses Stage 5 provider endpoints)
- Member enrollment lookup and product display
- Repricing sandbox (uses `/api/reprice-claim/` instead of direct contract selection)
- Contract product scope editor (links contracts to LOB/products)
- Batch repricing job submission and results viewer
- Network participation management (admin-grade CRUD for Stage 1 models)

---

## Cross-Stage Requirements

### Migration Standards
- All new FK columns on existing models: `null=True, blank=True`
- No column renames on existing tables
- Every migration must be reversible (`python manage.py migrate core 0032` must work)
- New tables use snake_case `db_table` names explicitly set

### Code Standards
- All new models: `created_at`, `updated_at` auto fields
- All currency: `DecimalField(max_digits=12, decimal_places=2)` — no `FloatField`
- All services return typed Python objects or `None` — never raw querysets from service layer
- All new API views: DRF `APIView` or `GenericAPIView` — no function-based views

### Test Requirements
- Each stage adds a test file: `tests/test_stage1_provider_domain.py`, etc.
- Each new service class gets a unit test file
- Context resolver integration test seeded against demo data
- The 43 existing tests must pass after every stage — checked in CI before merge

### Feature Flags
| Flag | Stage Introduced | Behavior |
|---|---|---|
| `FEATURE_CONTEXT_RESOLVER` | Stage 4 | Gates `/api/resolve-context/` and context resolution path |
| `FEATURE_REPRICE_API` | Stage 5 | Gates `/api/reprice-claim/` and batch endpoints |
| `FEATURE_TIERED_RESOLUTION` | Keep disabled | Enable in Stage 5 once network context is real |

---

## Summary Table

| Stage | Duration | New Models | New APIs | Risk |
|---|---|---|---|---|
| 0 — Engine hygiene | < 1 day | None | None | Zero |
| 1 — Provider domain | 2–3 weeks | Provider, Facility, ProviderAffiliation, ProviderNetworkParticipation, FacilityNetworkParticipation | None | Very low |
| 2 — Payer/Product/LOB/Network | 2–3 weeks | PayerOrganization, LineOfBusiness, Product, Network, ProductNetworkConfig, ContractProductScope | None | Low |
| 3 — Member/Enrollment + ClaimHeader | 2–3 weeks | Member, Enrollment | None | Low (all nullable) |
| 4 — Context Resolver | 3–4 weeks | None (DTO only) | `/api/resolve-context/` (debug) | Medium |
| 5 — Context-Driven APIs | 2–3 weeks | None | 7 new endpoints | Medium |
| 6 — UI | TBD | None | None | TBD |

**Total estimated backend timeline: ~12–16 weeks**  
**Engine changes: zero**  
**Existing API breakage: zero**
