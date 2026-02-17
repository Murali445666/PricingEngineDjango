# Status Tracking: Matrix Pricing Engine (PricingEngineDjango)

Scope: **PricingEngineDjango** only. "Pricing Engine V2" folder is out of scope.

---

## Done

| Area | Item | Notes |
|------|------|------|
| **Core domain** | Orchestrator | `PricingEngine.calculate_line(contract, PricingInput)` in `core/engine/orchestrator.py`. |
| **Core domain** | StrictRuleResolver | Best-match rule by `specificity_score`; uses PricingRule + PricingRuleCondition. |
| **Core domain** | PricingDataLoader | Builds PricingContext from FeeScheduleRate, RefProcedureCode, RefModifier. |
| **Core domain** | Strategies | RBRVS, FLAT_RATE, PERCENT_BILLED, STOP_LOSS, DRG, PER_DIEM, ANESTHESIA in `core/engine/strategies/`. |
| **Core domain** | Types | PricingInput, LineResult, PricingContext, PricingTrace in `core/engine/types.py`. |
| **Database** | Schema & migrations | ProviderOrganization, PayerNetwork, ProviderContract, PricingRule, PricingRuleCondition, FeeSchedule, FeeScheduleRate, RefProcedureCode, RefModifier (and related). |
| **Database** | Seeding | Management commands / seed scripts for test and demo data. |
| **Tests** | Engine tests | Tests in `tests/` (e.g. test_01_rbrvs through test_11_anesthesia, MPPR, modifiers, failure, dependency) using MatrixPricingEngine helper. |
| **API** | DRF installed | rest_framework (and corsheaders) in INSTALLED_APPS. |
| **API** | Serializers | PricingRequestSerializer, PricingResponseSerializer, ContractSerializer in `core/api/serializers.py`. |
| **API** | Views | PriceLineView (POST), ContractListView (GET) in `core/api/views.py`. |
| **API** | URLs | `/api/price-line/`, `/api/contracts/` in `core/api/urls.py`; `api/` included in `config/urls.py`. |

---

## To-Do

| Area | Item | Notes |
|------|------|------|
| **API** | Contract lookup | Align contract lookup with docs: plan expected lookup by integer `contract_id` (PK); current view uses `legacy_contract_number` when receiving `contract_id`. Decide and document one convention. |
| **API** | Response shape | Optionally add `trace_logs` and `engine_version` to PricingResponseSerializer if full traceability is required by clients. |
| **API** | Automated API test | Optional: add a test that POSTs to `/api/price-line/` with Matrix test data and asserts 200, `allowed_amount`, and `rule_id`. |
| **Docs** | Runbook / deployment | How to run migrations, seed data, and run tests in local/production. |
| **Future** | Retail recommendation | Separate domain using same patterns (rules, strategies, API) for portfolio. |
