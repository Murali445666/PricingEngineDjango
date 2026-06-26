# Version resolution fix — test plan

## Root cause (summary)

- **ClaimOrchestrator.run()** (orchestrator.py): When `config` was provided (simulate path), the code still set `version = resolve_active_contract_version(contract, service_date)` and used that for logging and the line loop. So the **active** version (e.g. 6) was shown in the log even when the request specified version_id=2 or 7.
- **Fix:** When `config` is present and has `config.version`, use `version = config.version`; otherwise resolve active version. Engine-start log now prints `Contract: {contract.pk} | Version: {version.version_id}` (no `version.id`; ContractVersion PK is `version_id`).

## Code changes

1. **core/engine/loader.py** — `resolve_contract_version(contract_id, version_id)` added; uses `ContractVersion.objects.get(contract_id=..., version_id=...)`; raises `ValueError` if not found (no fallback).
2. **core/engine/service.py** — `price_claim_with_version` uses `resolve_contract_version`; continues to raise `ValueError` for ARCHIVED or missing version; view returns 400.
3. **core/engine/orchestrator.py** — `ClaimOrchestrator.run()` uses `config.version` when config is provided; engine log line: `Mode: ... | Contract: ... | Version: ...` (version_id only).
4. **core/views.py** — `ContractVersionWorkflowView` get/post use `resolve_contract_version` for the requested version (same semantics as API).

## Manual test plan

1. **Payload version_id respected and logged**
   - POST `/api/price-claim-simulate/` with `contract_id=10`, `version_id=2` and valid claim.
   - **Expect:** Server log shows `[!] ENGINE STARTING - Mode: ... | Contract: 10 | Version: 2` (mode matches the DB for that version).
   - Repeat with `contract_id=14`, `version_id=7`; log should show `Contract: 14 | Version: 7`.

2. **Invalid version_id returns 400 (no silent fallback)**
   - POST with `contract_id=10`, `version_id=99999` (non-existent).
   - **Expect:** 400 response with body like `{"error": "Version 99999 not found for contract 10. ..."}`.
   - POST with valid `version_id` but for a different contract (e.g. version_id that belongs to contract 14, but send contract_id=10).
   - **Expect:** 400, no fallback to another version.

3. **Analyst UI uses same version and shows trace**
   - GET `/contracts/10/versions/2/ui/` (staff required).
   - **Expect:** 200, page shows version 2 info and simulation form.
   - POST the same URL with claim JSON; run simulation.
   - **Expect:** Simulation runs against version 2; server log shows `Version: 2`; UI shows staged behavior/trace if that version uses STAGED mode.

## Automated tests

- **core/tests/test_engine_version_resolution.py**
  - `test_resolve_contract_version_raises_when_version_not_found` — 99999/99999 raises ValueError.
  - `test_resolve_contract_version_raises_when_version_belongs_to_other_contract` — wrong contract_id raises ValueError.
  - `test_resolve_contract_version_returns_version_by_version_id` — correct contract_id + version_id returns the version (PK is version_id).

Run from project root (PricingEngineDjango):

```bash
python manage.py test core.tests.test_engine_version_resolution -v 2
```

If your environment uses a different settings module or PYTHONPATH, run tests the same way you run `manage.py runserver`.
