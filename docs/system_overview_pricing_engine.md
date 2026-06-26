# System Overview: Matrix Pricing Engine

This document describes the current state of the Matrix Pricing Engine as a product and technical system. It is intended for technical product managers and engineers who need to understand what the system does and how it works.

**Canonical:** [ROADMAP.md](ROADMAP.md) · [UPGRADE_PLAN.md](UPGRADE_PLAN.md) · [STATUS.md](STATUS.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [pricing_execution_flow.md](pricing_execution_flow.md)

---

## 1. Product Overview

### What the Matrix Pricing Engine Is

The Matrix Pricing Engine is a healthcare contract pricing system. It computes allowed amounts for medical claims according to the terms of configured contracts between payers and providers. The system applies rule-based logic, reference data (such as RVUs and fee schedules), and contract-specific overrides to produce deterministic, auditable pricing results.

### What Problem It Solves

Healthcare payers and providers need to price claims consistently against complex contract terms. Contracts may specify multiple pricing methodologies (e.g., fee schedule, percent of billed, DRG-based), carve-outs for specific procedure codes, stop-loss and outlier rules, blending of methodologies, and caps and floors. Doing this manually or with scattered logic is error-prone and hard to audit. The engine centralizes this logic, resolves the correct contract and version for each claim, runs a defined sequence of pricing steps, and returns both the allowed amounts and a trace of how they were computed.

### Type of Pricing

The engine performs **healthcare contract pricing**: it takes claim lines (procedure code, billed amount, units, modifiers, and related context) and a contract (or enough context to resolve one) and returns line-level and claim-level allowed amounts. It supports outpatient and inpatient-style logic, including line-level fee schedule and percent-of-billed pricing and claim-level methodologies such as DRG and stop-loss/outlier.

### How Analysts and Systems Interact

- **Analysts** use the web UI to configure contracts, manage rules and methodologies, run claim simulation (test claims against a chosen contract and version), and inspect contracts via the Contract Explorer. They can also run contract validation to detect configuration conflicts before pricing.
- **Systems** integrate via REST APIs: submit a claim (or batch of claims) with contract identifier and lines; receive a structured result with allowed amounts, status, and optional execution trace. Stored claims can be priced by claim ID; ad-hoc claims can be sent in the request body. Simulation and bulk endpoints support “what-if” and batch use cases.

### Main Capabilities

- **Contract configuration** — Contracts link providers and payers; they carry methodologies, pricing rules, carve-outs, stop-loss and outlier rules, blending rules, and caps/floors. Configuration can be scoped by contract version and effective date.
- **Rule-based pricing** — Pricing rules select by procedure code, claim type, and other conditions. Each rule is tied to a methodology (e.g., RBRVS, APC, flat rate). The resolver picks the best-matching rule per line; the loader builds pricing context from the rule and reference data; a strategy computes the allowed amount.
- **Claim simulation** — Analysts choose a contract and version, paste or edit claim JSON, and run pricing without persisting the claim. The result shows summary totals, per-line results, execution trace, and claim trace for debugging.
- **Contract Explorer** — A read-only view of a contract’s full structure: metadata, versions, and per-version methodologies, pricing rules (with conditions), carve-outs, caps/floors, blending rules, stop-loss and outlier rules, and open conflict counts.
- **Versioned contract logic** — Contracts can have multiple versions (e.g., by term or amendment). Each version can have its own methodologies, rules, carve-outs, and other elements. Pricing resolves the active version by service date or uses a specified version for simulation.
- **Cross-line pricing logic** — MPPR (Multiple Procedure Payment Reduction) logic can apply across lines: e.g., rank lines by allowed amount and apply different percentages to the first, second, and remaining procedures in a group.
- **Audit and traceability** — The engine records an execution trace (line and claim stages, methodology, rule applied, messages) and a claim trace (high-level log entries). Results expose applied rule IDs (e.g., stop-loss, outlier, cap/floor) so auditors can see why an amount was produced.

---

## 2. Core Concepts

### Contracts

A **contract** represents an agreement between a provider organization and a payer network. It has identity (contract_id, name, legacy number), status, effective dates, and carries all pricing configuration: methodologies, rules, carve-outs, stop-loss, outlier, blending, and caps/floors. When a claim is priced, the engine either uses the contract supplied in the request or resolves it from claim context (e.g., provider and service date).

### Contract Versions

A **contract version** is a time-bounded revision of a contract (e.g., a new term or amendment). Each version has a version number, effective start and end dates, and status (DRAFT, ACTIVE, SUPERSEDED, ARCHIVED). Methodologies, pricing rules, carve-outs, caps/floors, blending rules, stop-loss, and outlier rules can be tied to a specific version. For a given service date, the engine resolves the active version (or the caller specifies a version for simulation). Version-scoped rules and methodologies take precedence over contract-level ones when both exist.

### Pricing Rules

A **pricing rule** defines how a line (or set of lines) is priced. It is attached to a contract and optionally to a version. It has a rule type (e.g., BASE, ADJUSTMENT), a methodology code (or blank to inherit from contract methodology), effective dates, and optional **conditions** (e.g., procedure code, claim type, revenue code). The resolver evaluates conditions and specificity to choose the best rule for each line. The rule’s methodology and parameters (multiplier, flat rate, fee schedule reference, etc.) drive the strategy that computes the allowed amount.

### Methodologies (RBRVS, DRG, APC, etc.)

A **methodology** is the formula or basis used to compute an allowed amount. The engine supports several:

- **RBRVS** — Resource-based relative value system: RVUs (work, practice expense, malpractice) from reference data, adjusted by GPCI and conversion factor.
- **DRG** — Diagnosis-related group: typically used at claim level (e.g., base rate × DRG weight); can be configured per version.
- **APC** — Ambulatory payment classification: reference APC weights and payment rates.
- **ASP** — Average sales price: used for drug pricing from reference ASP data.
- **Flat rate** — A fixed amount per line (from the rule or a fee schedule/override).
- **Percent of billed** — Allowed amount = billed amount × a percentage.
- **Per diem** — Per-day rate from rule or reference table.

Contract-level **ContractMethodology** records define which methodology applies by date, claim type, and site of service. Rules can override with a specific methodology_code.

### Claim and Claim Line

A **claim** is a request to price a set of services. It has claim-level attributes (e.g., service date, claim type, contract, optional DRG code and facility/provider IDs) and a list of **lines**. A **claim line** has procedure code, billed amount, units, modifiers, and optionally cost amount and revenue code. The engine prices each line (subject to rules and carve-outs), then applies claim-level logic (e.g., DRG, stop-loss, outlier, blending, caps/floors) to produce a claim total and final status.

### Fee Schedules

A **fee schedule** is a set of procedure-code-to-rate mappings. Rules can reference a fee schedule by ID; the loader looks up the rate for the line’s procedure code and service date. Fee schedules are versioned and effective-dated so the engine can select the correct rate for the pricing date.

### Carve-outs

A **carve-out** is a per-version override for specific codes (e.g., CPT or HCPCS). It defines how a matching line is treated: **EXCLUDE** (zero allowed), **PCT_BILLED** (allowed = billed × percentage), or **FIXED_RATE** (allowed = fixed amount). Carve-outs are applied after base line pricing and before claim-level steps. Only one carve-out applies per line (by code match).

### Stop-loss

**Stop-loss** is a claim-level, cost-based protection. Rules define a cost threshold and a reimbursement percentage above that threshold. The engine sums line cost amounts, compares to the threshold, and if the cost exceeds it, can replace the claim total with a stop-loss payment. Stop-loss is evaluated before outlier; the first matching rule by priority wins.

### Outlier

**Outlier** is a claim-level, charge-based protection. Rules define a charge threshold and either a reimbursement percentage or a cost-to-charge ratio. If total billed (or another measure) exceeds the threshold, the claim total can be replaced by an outlier payment. Outlier runs after stop-loss.

### Blending

**Blending** combines or overrides amounts using a secondary basis. Rules specify blend type (ADD or OVERRIDE), scope (CLAIM or LINE), primary methodology, secondary methodology label, and a percentage. For CLAIM scope, ADD adds a percentage of total billed to the post–stop-loss/outlier total; OVERRIDE replaces the total with that percentage of billed. For LINE scope, blending applies per line and the new line amounts are summed. Blending runs after stop-loss and outlier and before caps/floors.

### Caps and Floors

**Caps and floors** clamp the final claim (or line) total. Rules have scope (e.g., CLAIM, LINE, DRG, APC), cap type (CAP, FLOOR, or percent-of-billed cap), and value or percentage. They are applied after blending as the final adjustment. Line-level caps/floors apply per line; claim-level caps/floors apply to the claim total.

### MPPR (Cross-line Logic)

**MPPR** (Multiple Procedure Payment Reduction) applies logic across lines. Definitions specify which procedure codes or code groups are in scope, how to rank lines (e.g., by allowed amount), and what percentages to apply to the first, second, and remaining lines. The engine identifies in-scope lines, ranks them, applies the percentages, and updates line amounts and claim total. MPPR runs after claim-level methodology (e.g., DRG) and before blending.

### Rule Conditions

**Rule conditions** narrow when a pricing rule applies. Each condition has an attribute (e.g., procedure_code, claim_type, revenue_code, billed_amount), an operator (e.g., EQ, IN, LT), and a value. The resolver evaluates conditions against the line and claim context; only rules whose conditions all pass are candidates. Condition matching plus specificity and version precedence determine the single rule used per line.

### How These Concepts Interact During Pricing

The engine first resolves the contract and version. It builds a **ContractPricingConfig** that holds all rules, methodologies, carve-outs, stop-loss, outlier, blending, caps/floors, and MPPR definitions effective for that contract, version, and service date. For each line, the resolver picks the best rule; the loader builds pricing context from that rule and reference data; the appropriate strategy computes a base allowed amount. Carve-outs and line-level caps/floors are applied per line. Line amounts are summed. Then claim-level steps run in order: optional claim-level DRG, stop-loss, outlier, MPPR, blending, and finally claim-level caps/floors. The result is a claim total, per-line results, and optional traces.

---

## 3. Claim Pricing Flow

The engine follows a fixed execution order so that results are deterministic and auditable.

1. **Contract resolution** — If the request does not already specify a contract, the engine resolves it from claim context (e.g., provider org/NPI and service date) using participation and scope matching. If the contract is provided (e.g., by ID), this step is skipped.

2. **Version resolution** — For production pricing, the active contract version for the claim’s service date is resolved (effective date in range, status ACTIVE). For simulation, the caller supplies a contract and version ID; that version is used provided it is not ARCHIVED.

3. **Configuration build** — A **ContractPricingConfig** is built (or taken from cache in bulk mode) for the contract, version, and service date. It loads rules, methodologies, stop-loss, outlier, carve-outs, caps/floors, blending rules, and MPPR definitions once so no per-line database lookups are needed for these.

4. **Line pricing** — For each claim line, the resolver selects the best pricing rule (conditions and effective date). The loader builds **PricingContext** (RVUs, fee schedule rate, conversion factor, etc.). The strategy for the rule’s methodology computes the base allowed amount. Result is stored as base and current allowed for that line.

5. **Carve-out application** — For each line, the engine checks whether the procedure code (and code type) matches a carve-out. If EXCLUDE, allowed is set to zero; if PCT_BILLED or FIXED_RATE, allowed is recalculated accordingly. Line-level state and trace are updated.

6. **Line-level cap/floor** — If the config has line-scope caps/floors, they are applied to each line’s current allowed amount. Trace entries record the application.

7. **Claim total** — The sum of line allowed amounts (after carve-outs and line caps/floors) is computed.

8. **Claim-level methodology** — If the version has claim-level DRG enabled and a DRG code is present, the engine can replace the claim total with a DRG-based payment (e.g., facility base rate × DRG weight). This runs before stop-loss and outlier.

9. **Stop-loss** — Stop-loss rules are evaluated in priority order. If total cost exceeds a rule’s threshold, the claim total can be set to the stop-loss payment and evaluation stops. Trace records the applied rule.

10. **Outlier** — Outlier rules are evaluated in priority order. If the charge (or other) threshold is exceeded, the claim total can be set to the outlier payment. Trace records the applied rule.

11. **Cross-line MPPR** — For each MPPR definition in config, in-scope lines are identified, ranked (e.g., by allowed amount), and primary/secondary/tertiary percentages are applied. Line amounts and claim total are updated. Trace entries record the phase.

12. **Blending** — Blending rules are applied: ADD or OVERRIDE at CLAIM or LINE scope, using the configured percentage of billed or current total. Claim total (and optionally line amounts) is updated. Trace records blending.

13. **Claim-level cap/floor** — Claim-scope (and any DRG/APC-scope) caps and floors are applied to the claim total. The result is clamped to the floor and cap. Trace records the applied cap/floor rule.

14. **Final result** — The engine returns a **ClaimPricingResult**: claim total, final total (after caps/floors), per-line results (allowed amount, methodology, rule ID, carve-out and blending where applicable), status, and optional execution_trace and claim_trace.

Each step has a clear purpose: contract/version ensure the right terms; config load avoids repeated queries; line pricing applies the correct methodology per line; carve-outs and line caps handle code-specific and line-level limits; claim-level steps apply financial protections and blending; caps/floors provide the final guardrails.

---

## 4. Pricing Engine Architecture

### ClaimPricingService

**ClaimPricingService** is the single entry point for all claim and line pricing. No API or other service should call the orchestrator or line orchestrator directly. The service:

- **price_claim** — Prices a claim (stored or built from request). Resolves contract and version if needed, builds or reuses config, and calls the claim orchestrator.
- **price_claim_with_version** — Prices a claim against an explicit contract and version (simulation). Bypasses active-version resolution; builds config from that version.
- **price_stored_claim** — Prices a claim that already exists as a ClaimHeader (and lines). Resolves contract from participation if the header has no contract.
- **price_claims_bulk** — Prices many claims in one call. Batches contract and version resolution and reuses **ContractPricingConfig** per (contract, version, service_date) to minimize database work.
- **price_line** — Prices a single line (e.g., for “price this line” tools). No claim-level version or config; uses contract and optional version only.

All claim flows go through the same orchestration path so behavior is consistent and traceable.

### ClaimOrchestrator

**ClaimOrchestrator** runs the canonical claim pricing sequence. It receives a **ClaimPricingInput** (contract, lines, service date, claim type, etc.) and an optional **ContractPricingConfig**. If config is not provided, it resolves the active version and asks the loader to build config. It then:

- Builds an execution context (line states, claim total, trace list).
- Preloads carve-outs into a lookup by code for fast per-line application.
- For each line: calls **LineOrchestrator** to get base allowed amount, applies carve-out, applies line-level cap/floor, appends line result and trace entries.
- Sums line allowed amounts.
- Runs claim-level DRG (if enabled), then stop-loss, then outlier, then MPPR, then blending, then claim-level caps/floors.
- Returns **ClaimPricingResult** with totals, line results, status, and traces.

The orchestrator does not implement the actual pricing formulas; it delegates line pricing to **LineOrchestrator** and strategy modules, and uses small helper functions for carve-out, cap/floor, and blending so the main flow stays readable and the order is guaranteed.

### Resolver

The **resolver** selects the single **PricingRule** to use for a given line. It is given the contract, optional version, and optional prebuilt config. When config is provided, it filters config’s rules by effective date and (if versioned) prefers version-scoped rules and orders by specificity. When config is not provided, it queries the database with the same logic. It then iterates rules in order and evaluates **conditions** against the line (procedure code, claim type, billed amount, etc.). The first rule whose conditions all pass is chosen. That rule’s methodology and parameters drive the rest of the line’s pricing.

### Loader

The **loader** has two main roles.

- **Contract/version resolution** — **resolve_contract_for_claim** finds a contract when the claim has no contract ID, using provider participation and scope matching. **resolve_active_contract_version** returns the active version for a contract and service date. **resolve_contract_version** returns a specific version by ID (for simulation).
- **Config and context** — **build_contract_pricing_config_from_db** (and the version-based variant) builds **ContractPricingConfig**: rules, methodologies, stop-loss, outlier, carve-outs, caps/floors, blending, MPPR definitions, and base rates, all filtered by effective date and optionally version. **PricingDataLoader** (used during line pricing) builds **PricingContext** from the chosen rule and reference data: fee schedule rates, RVUs, GPCI, DRG weight, modifier adjustments, etc. The loader uses config when provided to avoid querying the database again; it also caches reference lookups within a request to avoid N+1 queries.

### Strategy Modules

Each pricing methodology is implemented by a **strategy** that takes **PricingContext** and returns an allowed amount (and optional details). The engine has strategies for:

- **RBRVS** — Work, PE, and MP RVUs from context, GPCI-adjusted, multiplied by conversion factor; optional modifier adjustments.
- **DRG** — Base rate × DRG relative weight (typically used at claim level via a claim plugin; line-level DRG can use the same idea).
- **APC** — APC relative weight and payment rate from reference data.
- **ASP** — Drug pricing from ASP reference data.
- **Flat rate** — Fixed amount from rule or fee schedule lookup.
- **Percent of billed** — Billed amount × percentage from context.
- **Per diem** — Per-day rate × units (from rule or reference).

Claim-level methodologies (e.g., one payment per claim for DRG) are implemented as **claim plugins** that run inside the orchestrator after line pricing and can replace the claim total. The line-level strategies are invoked by **LineOrchestrator** after the resolver returns a rule and the loader has built context.

---

## 5. Configuration Loading

### ContractPricingConfig

**ContractPricingConfig** is an in-memory, request-scoped object that holds everything the engine needs to price a claim for a given contract, version, and service date: rules (and rules partitioned by stage), methodologies, stop-loss rules, outlier rules, carve-outs, claim-level and line-level caps/floors, blending rules, MPPR definitions, and base rates (e.g., DRG/APC). It is built once per pricing run (or reused across multiple claims in bulk). The orchestrator and line orchestrator receive this config so the resolver and loader do not hit the database again for rules, methodologies, or version-scoped data during the line loop.

### Snapshot vs Database Loading

- **Database loading** — **build_contract_pricing_config_from_db** (and the version-based variant) loads the config directly from the database: rules with conditions, methodologies with fee schedule, stop-loss, outlier, carve-outs, caps/floors, blending, MPPR. Used for single-claim pricing and when no snapshot exists.
- **Snapshot** — The **contract snapshot** service can build a cached, serializable summary of a contract’s runtime config (methodologies, rule IDs, fee schedule refs, stop-loss, outlier, carve-outs, etc.). **get_or_build_snapshot** returns this for display or tooling. The snapshot can also be used to build a **ContractPricingConfig** (e.g., for bulk runs) so that repeated config builds for the same contract are avoided. Cache invalidation is triggered when contract configuration (methodologies, rules, etc.) changes.

### How Rules, Methodologies, and Caps Are Loaded

Rules are loaded for the contract (and version if present), filtered by effective date, and optionally partitioned by rule_type (BASE, ADJUSTMENT) for staged resolution. Methodologies are loaded for the contract/version and effective date, ordered by priority and date, with fee schedule and contract term selected to avoid N+1. Stop-loss and outlier rules are loaded for the contract/version and effective date and ordered by priority. Carve-outs, caps/floors, and blending rules are loaded per version and effective date. MPPR definitions are loaded with their scopes (code groups or procedure codes). All of this is done inside the loader when building **ContractPricingConfig**; the result is immutable for the duration of the run.

### Why This Improves Performance

Building config once and reusing it eliminates repeated queries for the same contract and version. In bulk pricing, config is cached per (contract_id, version_id, service_date), so many claims that share that key reuse one config. Reference data (RVUs, fee schedules, DRG, etc.) is also cached per execution in the data loader so each line does not trigger new lookups. Together, this keeps query count low and makes bulk and single-claim pricing efficient.

---

## 6. API Layer

### Claim Pricing APIs

- **POST /api/price-claim/** — Price a single claim in the request body. Inputs: contract_id (or legacy number), lines (procedure_code, billed_amount, units, modifiers, etc.), optional service_date, pricing_date, claim_type. The engine resolves the active version, builds config, and runs full orchestration. Returns claim total, line results, status, applied rule IDs (stop-loss, outlier, cap/floor, blending), and optional traces. Used for ad-hoc claim pricing and integration tests.

- **POST /api/price-claim-simulate/** — Same as price-claim but the caller supplies contract_id and version_id. The engine uses that version (DRAFT, ACTIVE, or SUPERSEDED; ARCHIVED is rejected) and does not resolve the active version. Used by the Claim Simulation UI so analysts can test a specific version.

- **POST /api/price-claims-bulk/** — Price many claims in one request. Input: array of claims, each with contract_id, lines, optional service_date and claim_type. The service batches contract and version resolution and reuses **ContractPricingConfig** per (contract, version, service_date). Returns an array of results in the same order. Used for batch simulation and bulk “what-if” runs.

- **GET /api/claims/<id>/price/** — Price a stored claim by ID. The claim (ClaimHeader and lines) is loaded; if it has no contract, contract is resolved from participation/scope. Same orchestration as price-claim. Returns the same result shape.

- **POST /api/price-line/** — Price a single line. Inputs: contract_id, procedure_code, billed_amount, optional units, modifiers, service_date, claim_type. No claim-level version resolution or config; used for “price this line” tools and testing.

### Contract APIs

- **GET /api/contracts/** — List contracts (e.g., active). Returns contract_id, name, status, legacy number, and open conflict counts (errors and warnings). Used by the UI for contract selectors and lists.

- **GET /api/contracts/<id>/** — Contract detail: metadata, methodologies, outlier rules, stop-loss rules, and related data. Used when editing or viewing a single contract.

- **GET /api/contracts/<id>/explorer/** — Full contract tree: `contract` {id, legacy_contract_number, contract_name}, `open_conflict_counts` {errors, warnings}, `versions` with `rules` (each with conditions), methodologies, carveouts, cap_floors, blending_rules, stop_loss_rules, outlier_rules. **GET** same path **?export=csv** returns a flat CSV of contract/version/rule rows (use `export=` not `format=`). Read-only; no pagination.

- **GET /api/contracts/<id>/rules/** — List pricing rules for the contract (with conditions when loaded). Used by rules UI and reporting.

- **GET /api/contracts/<id>/snapshot/** — Materialized snapshot of contract runtime config (methodologies, rule IDs, stop-loss, outlier, carve-outs, etc.). Used for caching and tooling.

Other contract-related endpoints exist for methodologies, outlier rules, stop-loss rules, conflicts, and version lifecycle (e.g., activate, archive). Reference data (fee schedules, procedure codes, DRG, APC, etc.) and rules (list, detail, history, conflicts) have their own endpoints as needed by admin and UI.

---

## 7. Claim Simulation UI

The Claim Simulation page lets analysts run pricing against a chosen contract and version without storing a claim.

### Purpose

Analysts select a contract and a version, enter or paste claim JSON (service date, claim type, and lines with procedure code, billed amount, units, modifiers), and click Run Simulation. The frontend sends the payload to **POST /api/price-claim-simulate/** and displays the result. This supports testing configuration changes, validating behavior for specific procedure mixes, and debugging why an amount was produced.

### Selecting Contract and Version

The contract dropdown is filled from **GET /api/contracts/**. The version is chosen by entering a version ID (numeric); the UI does not yet call a dedicated “versions for contract” list endpoint. If such an endpoint is added, the version selector can be a dropdown.

### Entering Claim JSON

A text area holds the claim JSON. It can be edited or pasted. A sample claim (e.g., two lines with procedure codes and billed amounts) is shown by default. The JSON must include a **lines** array; each line has procedure_code, billed_amount, and optionally units and modifiers. Invalid JSON is caught before the API is called and an inline error is shown.

### Running Pricing

On Run, the frontend parses and validates the JSON, then POSTs **{ contract_id, version_id, claim }** to **/api/price-claim-simulate/**. Network and API errors are shown; on success, the result sections are rendered.

### Result Sections

- **Summary** — contract_id, version_id, status, total_allowed, final_total_allowed, original_total_allowed, pre_cap_total_allowed, and IDs of applied cap/floor, stop-loss, and outlier rules (if any).
- **Line Results** — Table of per-line status, methodology, rule_id, allowed_amount, base_allowed_amount, blended_allowed_amount, carveout_applied, carveout_id.
- **Execution Trace** — Table of trace entries: stage (LINE/CLAIM), phase, line_index, rule_id, methodology_code, message. Shows the order of operations for auditing.
- **Claim Trace** — List of high-level log messages (e.g., “CLAIM_DRG_APPLIED”, “stop-loss applied”).

Together these sections answer “what did we get?” and “how did we get it?”

---

## 8. Contract Explorer UI

The Contract Explorer is a read-only page that shows the full structure of a contract.

### What It Shows

- **Contract metadata** — Contract ID, name, status, legacy number, effective dates, and open conflict counts (with a link to the contract’s conflict panel if there are errors or warnings).
- **Versions** — For each version: version number, ID, status, effective dates, and collapsible sections for:
  - **Methodologies** — Type, effective/termination dates, priority, claim type, site of service, and related IDs.
  - **Pricing rules** — Rule ID, name, methodology, type, status, and condition count (with conditions available in the data).
  - **Carve-outs** — Code type, code value, methodology (EXCLUDE, PCT_BILLED, FIXED_RATE), percentage or rate, status.
  - **Caps/floors** — Scope, cap type, value, percentage, code value, priority, effective dates, status.
  - **Blending rules** — Blend type, scope, primary/secondary methodology, percentage, priority, status.
  - **Stop-loss rules** — Cost threshold, reimbursement percentage, priority, effective dates.
  - **Outlier rules** — Threshold amount, scope, reimbursement percentage or cost-to-charge ratio, priority, effective dates.

Data is loaded from **GET /api/contracts/<id>/explorer/**. If the contract has no versions or a version has no rules, the corresponding tables are empty; the page does not break.

### How Analysts Use It

Analysts use the Contract Explorer to see everything that affects pricing for a contract in one place: which methodologies and rules exist, which codes are carved out, what caps and blending apply, and what stop-loss and outlier rules are configured. It supports auditing, onboarding, and debugging (“why did this line use that rule?”). The open conflict count and link help them jump to validation results. The page does not support editing; configuration is done elsewhere (admin or future config UI).

---

## 9. Execution Trace and Auditability

The engine records two kinds of trace information.

### Execution Trace

The **execution_trace** is a list of structured entries. Each entry has:

- **stage** — LINE or CLAIM.
- **phase** — e.g., BASE, ADJUSTMENT, CARVEOUT, LINE_CAP_FLOOR, CLAIM_METHOD, STOP_LOSS, OUTLIER, BLENDING, CAP_FLOOR.
- **line_index** — For line-stage entries, the zero-based line index.
- **rule_id** — The pricing rule (or stop-loss, outlier, cap/floor rule) applied.
- **methodology_code** — The methodology used (e.g., RBRVS, APC).
- **message** — Short text (e.g., procedure_code and allowed_amount, or “stop-loss applied”).

Trace entries are appended in order as the orchestrator runs: one per line for base pricing and carve-out/cap, then claim-level entries for DRG, stop-loss, outlier, blending, and cap/floor. The simulation API returns this list so the UI can show a table or timeline.

### Claim Trace

The **claim_trace** is a list of human-readable log strings (e.g., “CLAIM_DRG_APPLIED drg_code=… claim_total=…”, “stop-loss applied”, “blending applied”). It summarizes the main claim-level decisions without the full structure of the execution trace.

### Why This Matters

Traces support debugging (“which rule was used for line 2?”), auditing (“prove how the allowed amount was computed”), and support (“explain to a provider why the amount changed”). The execution trace is stable and machine-readable so tools can parse it; the claim trace is quick to scan. Together with fields like applied_stop_loss_rule_id and applied_cap_floor_id in the result, the system provides a clear audit trail for each run.

---

## 10. Current Capabilities

The following are implemented and in use:

- **Contract versioning** — Multiple versions per contract with effective dates and status; version-scoped methodologies, rules, carve-outs, stop-loss, outlier, blending, caps/floors.
- **Rule resolution** — StrictRuleResolver with conditions, specificity, and version precedence; effective dating; claim_type and optional filters.
- **Carve-outs** — EXCLUDE, PCT_BILLED, FIXED_RATE by code type/value; applied after base line pricing.
- **Stop-loss** — Claim-level, cost-based; threshold and reimbursement percentage; priority ordering.
- **Outlier** — Claim-level, charge-based; threshold and reimbursement percentage or cost-to-charge ratio; PER_CLAIM scope (PER_LINE not implemented).
- **MPPR** — Cross-line definitions with code groups or procedure codes; rank by allowed amount; primary/secondary/tertiary percentages.
- **Blending** — ADD and OVERRIDE; CLAIM and LINE scope; applied after stop-loss/outlier, before caps.
- **Caps and floors** — Claim and line scope; CAP, FLOOR, PCT_BILLED_CAP; effective dates and priority.
- **Claim simulation** — POST /api/price-claim-simulate/ and Claim Simulation UI (contract, version, claim JSON, result sections).
- **Contract Explorer** — GET /api/contracts/<id>/explorer/ and Contract Explorer UI (metadata, versions, methodologies, rules, carve-outs, caps/floors, blending, stop-loss, outlier).
- **Stored-claim and batch pricing** — Price by claim ID; price-claim and price-claims-bulk with config reuse.
- **Contract resolution** — By participation and scope when claim has no contract.
- **Conflict detection** — Validation service and validate-contract endpoint; methodology collision, carve-out overlap, blending cycle, scope overlap; results stored and shown in UI.
- **Unified orchestration** — Single path through ClaimPricingService and ClaimOrchestrator for all claim flows; no duplicate logic.
- **Traceability** — Execution trace and claim trace; applied rule IDs in result.

---

## 11. Known Limitations / Not Yet Implemented

- **PER_LINE outlier** — Outlier is implemented only for PER_CLAIM scope. Per-line outlier is not supported.
- **Add-on CPT dependencies** — Logic that depends on “add-on” procedure code relationships (e.g., base + add-on rules) is not fully modeled.
- **Advanced modifier precedence** — Modifier handling follows current loader and strategy behavior; formal precedence tables or complex modifier stacks are not documented as a completed feature.
- **Plan/employer hierarchy overrides** — No explicit plan or employer hierarchy that overrides contract or version selection; resolution is by provider participation and scope only.
- **Advanced cross-line logic combinations** — MPPR is implemented; other cross-line patterns (e.g., multiple MPPR types with complex precedence) may require extension.
- **Claim template save/load** — The Claim Simulation UI does not yet save or load claim templates.
- **Bulk simulation UI** — No dedicated UI for submitting large batches of claims for simulation; bulk is available via API only.
- **Contract Explorer CSV scope** — CSV export is rule-oriented flat rows; other entities (carve-outs only in JSON tree).
- **Blending DAG visualization** — A node-edge graph for blending rules is noted as future work; explorer shows blending rules as tables only.
- **Enterprise packaging** — Multi-tenant isolation, API versioning, and formal batch job and deployment patterns are planned (e.g., Step 13) but not yet delivered.

---

## 12. Directory Overview

- **core/** — Main Django app. Contains models (contracts, rules, claims, reference data, validation), admin registration, and URL wiring that includes the API.

- **core/engine/** — Pricing engine implementation. **service.py** defines ClaimPricingService. **orchestrator.py** defines ClaimOrchestrator and LineOrchestrator and helpers for carve-out, cap/floor, blending, and MPPR. **config.py** defines ContractPricingConfig and claim/line input types. **loader.py** handles contract/version resolution and config building; **PricingDataLoader** builds PricingContext for a line. **resolver.py** implements StrictRuleResolver. **types.py** defines PricingInput, PricingContext, LineResult, ClaimPricingResult, ExecutionContext, TraceEntry. **claim_strategies.py** implements claim-level plugins (e.g., DRG). Strategy modules for line-level methodologies (RBRVS, APC, etc.) and conditions live in the engine or adjacent modules.

- **core/api/** — REST API. **views.py** contains all API views (contracts, rules, claims, pricing, validation, conflicts, explorer, version lifecycle). **urls.py** wires paths to views. **serializers.py** defines request/response serializers for pricing, contracts, rules, methodologies, explorer, and related models.

- **core/services/** — Backend services used by the engine and API. **contract_explorer_service.py** loads the full contract tree for the explorer. **contract_snapshot.py** builds and caches contract snapshot. **validation_service.py** runs conflict checks. **rule_lifecycle_service.py** handles version activate/archive. **rule_conflict.py** supports rule conflict checks. **condition_validation_service.py** validates condition schemas.

- **frontend/** — React single-page application (Vite, TypeScript, React Router, TanStack Query, Tailwind). **src/features/** contains feature-specific pages (pricing sandbox, contracts, contract explorer, rules, claim simulation, batch monitor, admin). **src/services/** holds API clients. **src/shared/ui/** holds shared UI components. The frontend talks to the Django backend via the configured API base URL (e.g., proxy to /api in development).

---

## 13. How to Run the System

### Backend

From the project root (the directory containing `manage.py`):

```bash
python manage.py runserver
```

The API is served at the configured host and port (e.g., http://localhost:8000). The API base path is typically `/api/` (e.g., http://localhost:8000/api/contracts/).

### Frontend

From the frontend directory (e.g., `frontend/` or `PricingEngineDjango/frontend/`):

```bash
npm install
npm run dev
```

The dev server usually runs at http://localhost:5173 and proxies API requests to the backend. Check the frontend’s environment or Vite config for the exact API base URL.

### Testing

From the project root:

```bash
python manage.py test
```

To run a subset of tests (e.g., contract explorer API tests):

```bash
python manage.py test core.tests.test_contract_explorer
```

Tests use the test database (created and destroyed automatically). No frontend test commands are specified here; add them per your frontend test setup if needed.

---

*This document reflects the state of the Matrix Pricing Engine as of the last update. For roadmap and step-by-step status, see the Unified Roadmap and related docs in the repository.*
