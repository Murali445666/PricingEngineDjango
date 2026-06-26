# Step-by-Step Guide: Test LOBA (Lesser of Billed and Allowed) in Django Admin and Simulation

This guide uses your exact Django Admin labels and the Simulation API to test a LOBA rule: **procedure 00100**, **billed $100**, **base (fee schedule) $150** → engine should return **allowed $100**.

---

## Prerequisites

- A **Provider contract** and a **Contract version** that uses **Staged** pricing engine mode.
- The contract version must be **DRAFT**, **ACTIVE**, or **SUPERSEDED** (simulation rejects ARCHIVED).

If you already have a contract and version (e.g. from seed_demo), note their **IDs** (contract_id and version_id). You will use them when creating rules and when calling the simulate API.

---

## 1. Fee Schedule Setup — $150.00 rate for procedure code 00100

### 1.1 Create the Fee Schedule

1. In Django Admin, go to **Core** → **Fee schedules**.
2. Click **Add Fee schedule**.
3. Fill in:
   - **Name:** e.g. `LOBA Test Schedule`
   - **Effective date:** e.g. `2026-01-01` (or leave blank)
   - **Version:** e.g. `1`
4. Click **Save**. Note the **Fee schedule ID** (e.g. `15`) from the list or the URL after save.

### 1.2 Add the $150.00 rate for procedure code 00100

1. Go to **Core** → **Fee schedule rates**.
2. Click **Add Fee schedule rate**.
3. Fill in:
   - **Fee schedule:** click the magnifying glass and select the schedule you created (e.g. *LOBA Test Schedule*), or enter its ID.
   - **Code id:** `00100`
   - **Rate amount:** `150.00`
   - **Effective start date:** leave blank or e.g. `2026-01-01`
   - **Effective end date:** leave blank or e.g. `2026-12-31`
   - **Year:** leave blank or e.g. `2026`
4. Click **Save**.

You now have a fee schedule with a **$150.00** rate for procedure code **00100**.

---

## 2. Contract Version — Set Staged engine mode

LOBA uses the **STAGED** engine (BASE then ADJUSTMENT). Ensure the version uses it:

1. Go to **Core** → **Contract versions**.
2. Open the **Contract version** you will use for this test (or create one for the contract).
3. Set **Pricing engine mode** to **Staged**.
4. Set **Effective start date** / **Effective end date** so they cover your test service date (e.g. `2026-01-01` to `2026-12-31`).
5. Click **Save**. Note the **Version id** (from list or URL).

---

## 3. BASE Rule Setup — FLAT_RATE using the Fee Schedule

1. Go to **Core** → **Pricing rules**.
2. Click **Add Pricing rule**.
3. Fill in exactly:
   - **Contract:** select the contract you are using for the test.
   - **Version:** select the **Contract version** that has **Pricing engine mode = Staged** (same version as in step 2).
   - **Rule name:** e.g. `LOBA BASE 00100`
   - **Rule type:** `BASE`
   - **Methodology code:** `FLAT_RATE`
   - **Base fee schedule:** select the **Fee schedule** you created (e.g. *LOBA Test Schedule*). This makes the engine look up the rate by procedure code (e.g. $150 for 00100) instead of a fixed flat rate.
   - **Multiplier:** `1.0000` (default)
   - **Flat rate:** leave **blank** (rate will come from the fee schedule).
   - **Status:** `Active`
   - **Effective start date:** e.g. `2026-01-01`
   - **Effective end date:** e.g. `2026-12-31` or leave blank
4. Click **Save**. Note the **Rule id**.
5. Add **one condition** so this rule matches line 00100:
   - Go to **Core** → **Pricing rule conditions**.
   - Click **Add Pricing rule condition**.
   - **Pricing rule:** select the rule you just created (e.g. *LOBA BASE 00100*).
   - **Attribute name:** `procedure_code` (or `code` if your engine maps it).
   - **Operator:** `EQ`
   - **Attribute value:** `00100`
   - Click **Save**.

BASE is done: for procedure **00100** the engine will use the fee schedule and get **$150.00** as base allowed.

---

## 4. ADJUSTMENT Rule Setup — PCT_BILLED with `billed_amount LT @base_allowed_amount`

1. Go to **Core** → **Pricing rules**.
2. Click **Add Pricing rule**.
3. Fill in:
   - **Contract:** same contract as the BASE rule.
   - **Version:** **same version** as the BASE rule (Staged).
   - **Rule name:** e.g. `LOBA ADJUSTMENT lesser of billed`
   - **Rule type:** `ADJUSTMENT`
   - **Methodology code:** `PCT_BILLED`
   - **Multiplier:** `1.0000` (100% of billed when condition matches = lesser of billed and allowed).
   - **Base fee schedule:** leave blank.
   - **Flat rate:** leave blank.
   - **Status:** `Active`
   - **Effective start date:** e.g. `2026-01-01`
   - **Effective end date:** e.g. `2026-12-31` or blank
4. Click **Save**.
5. Add **one condition** that uses the **dynamic reference** `@base_allowed_amount`:
   - Go to **Core** → **Pricing rule conditions**.
   - Click **Add Pricing rule condition**.
   - **Pricing rule:** select the ADJUSTMENT rule you just created.
   - **Attribute name:** `billed_amount`
   - **Operator:** `LT`
   - **Attribute value:** `@base_allowed_amount`  
     (no space; the `@` means “use the value of base_allowed_amount from the line context”).
   - Click **Save**.

ADJUSTMENT is done: when **billed_amount** is less than **base_allowed_amount**, the engine will apply PCT_BILLED 100% and return the billed amount ($100) as allowed.

---

## 5. Simulation Test — Prove $100 allowed (not $150)

Use the **Simulation** API so pricing runs against your **specific version** (with STAGED and your two rules).

### 5.1 Where to call the API

- **URL:** `POST /api/price-claim-simulate/`  
  (e.g. `http://localhost:8000/api/price-claim-simulate/` if your app is at port 8000.)
- If you have a **Simulation UI** that posts to this endpoint, paste the JSON below into the body (or the form that builds it). Otherwise use **curl**, **Postman**, or the **Django REST framework browsable API** at that URL.

### 5.2 Exact JSON payload

Replace `CONTRACT_ID` and `VERSION_ID` with your actual contract PK and contract version PK (the one with Staged mode and the two rules above).

```json
{
  "contract_id": CONTRACT_ID,
  "version_id": VERSION_ID,
  "claim": {
    "lines": [
      {
        "procedure_code": "00100",
        "billed_amount": "100.00",
        "units": 1,
        "modifiers": []
      }
    ],
    "service_date": "2026-06-15"
  }
}
```

**Example** (contract_id = 10, version_id = 5):

```json
{
  "contract_id": 10,
  "version_id": 5,
  "claim": {
    "lines": [
      {
        "procedure_code": "00100",
        "billed_amount": "100.00",
        "units": 1,
        "modifiers": []
      }
    ],
    "service_date": "2026-06-15"
  }
}
```

### 5.3 What to expect in the response

- **Status:** 200.
- **Body:** includes `"simulation": true`, `"version_id": <your version id>`, and a `result` object (claim-level and line-level pricing).
- In **result**, for the single line:
  - **procedure_code:** `00100`
  - **allowed_amount:** `100.00` (not 150.00) — LOBA applied: lesser of billed ($100) and base allowed ($150).
  - **status:** typically a success status (e.g. not DENIED_NO_RULE or DENIED_CALCULATION_ERROR).

If **allowed_amount** is **100.00**, the LOBA rule is working: the engine used BASE ($150 from fee schedule), then ADJUSTMENT with `billed_amount LT @base_allowed_amount` and PCT_BILLED 1.0 to produce **$100**.

---

## Quick reference: Admin labels used

| Area | Label / Field |
|------|----------------|
| Fee schedule | **Core → Fee schedules** → Name, Effective date, Version |
| Fee schedule rate | **Core → Fee schedule rates** → Fee schedule, Code id, Rate amount |
| Contract version | **Core → Contract versions** → Pricing engine mode = **Staged** |
| Pricing rule | **Core → Pricing rules** → Contract, Version, Rule type, Methodology code, Base fee schedule, Flat rate, Status, Effective start/end date |
| Pricing rule condition | **Core → Pricing rule conditions** → Pricing rule, Attribute name, Operator, Attribute value |

---

## Troubleshooting

- **Allowed is 150 instead of 100:**  
  - Check ADJUSTMENT rule **Attribute value** is exactly `@base_allowed_amount` (no space, no typo).  
  - Check **Version** on both rules is the same and that version’s **Pricing engine mode** is **Staged**.  
  - Check **service_date** in the payload is within both rules’ effective dates.

- **DENIED_NO_RULE or no match:**  
  - Ensure BASE and ADJUSTMENT rules have **one condition each** (procedure_code EQ 00100, and billed_amount LT @base_allowed_amount).  
  - Ensure contract_id and version_id in the JSON match the contract and version that own the rules.

- **Fee schedule rate not used (allowed wrong or zero):**  
  - Ensure the BASE rule’s **Base fee schedule** is set to the schedule that has a **Fee schedule rate** with **Code id** `00100` and **Rate amount** `150.00`.  
  - Ensure **service_date** falls within the rate’s effective dates if you set them.
