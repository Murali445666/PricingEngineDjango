# Analyst UI — test URL and JSON

Use the data below to test the analyst UI and the simulate API. Contract **10** (DEMO_OP_FLAT_OUTPATIENT) **version 2** has a rule for procedure **00102** (FLAT 00102, 97.31).

---

## 1. Django analyst UI (browser)

**URL (open in browser):**
```
http://localhost:8000/contracts/10/versions/2/ui/
```
- Requires staff login. If you get 302, log in at `/admin/` then retry.
- Replace `localhost:8000` with your server host/port if different.

**JSON to paste in the “Claim JSON” textarea (then click Run simulation):**
- The page uses **only the claim payload** (no `contract_id`/`version_id`; those come from the URL).

```json
{
  "lines": [
    { "procedure_code": "00102", "billed_amount": "150.00", "units": 1, "modifiers": [] }
  ],
  "service_date": "2026-06-01"
}
```

---

## 2. Simulate API (Postman / curl / frontend)

**URL:**
```
POST http://localhost:8000/api/price-claim-simulate/
```

**Headers:**
- `Content-Type: application/json`

**JSON body:**
```json
{
  "contract_id": 10,
  "version_id": 2,
  "claim": {
    "service_date": "2026-06-01",
    "claim_type": "OP",
    "lines": [
      { "line_id": "1", "procedure_code": "00102", "billed_amount": "150.00", "units": 1, "modifiers": [] }
    ]
  }
}
```

**curl example:**
```bash
curl -X POST http://localhost:8000/api/price-claim-simulate/ \
  -H "Content-Type: application/json" \
  -d "{\"contract_id\":10,\"version_id\":2,\"claim\":{\"service_date\":\"2026-06-01\",\"claim_type\":\"OP\",\"lines\":[{\"procedure_code\":\"00102\",\"billed_amount\":\"150.00\",\"units\":1,\"modifiers\":[]}]}}"
```

---

## 3. Other contracts/versions from your table

| Contract name                 | contract_id | version_id | Example procedure_code |
|------------------------------|-------------|------------|------------------------|
| DEMO_OP_FLAT_OUTPATIENT      | 10          | 2          | 00102, 00100, 0001F    |
| DEMO_PRO_RBRVS_2026          | 9           | 1          | 00102, 00100           |
| DEMO_HYBRID_ENTERPRISE_COMPLEX | 14       | 6 or 7     | 00102, 0001F           |
| DEMO_IP_PER_DIEM             | 13          | 5          | 0001F                  |
| DEMO_IP_DRG_2026             | 12          | 4          | 001, 002               |

For the **Django UI**, use URL `/contracts/<contract_id>/versions/<version_id>/ui/` and the same claim JSON shape (lines + service_date). For the **API**, use the same body shape with the chosen `contract_id` and `version_id`.

---

## 4. If you still see “Simulation error”

- The workflow view and the API now put the **real error message** in the response (workflow: in the page; API: in `{"error": "..."}`).
- Check the **browser page** for the exact message under the form, or the **API response body**.
- Typical causes: version not found, ARCHIVED version, or an exception inside the engine (e.g. missing methodology/fee schedule). Share that message to debug further.
