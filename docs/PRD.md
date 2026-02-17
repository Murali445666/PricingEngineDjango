# Product Requirements: Matrix Enterprise Healthcare Pricing Engine

## Summary

The **Matrix** project is a portfolio-grade, enterprise healthcare pricing engine built with Hexagonal Architecture. It demonstrates senior-level engineering through domain-driven design, strategy patterns, and metadata-driven configuration. Delivery is organized in a **7-Phase Master Roadmap** (see [ROADMAP.md](../ROADMAP.md)).

---

## Strategic Goals (Aligned to Roadmap)

1. **Calculation kernel (Phase 1)**  
   Deterministic, extensible, testable domain layer with stable request/result contracts, metadata-driven resolver, pluggable strategies, and structured tracing.

2. **Pricing as a service (Phase 2)**  
   REST APIs for single-line and multi-line pricing and contract lookup, with a basic internal pricing sandbox UI and DTO versioning.

3. **Governance and transparency (Phase 3)**  
   Rule lifecycle (Draft / Approved / Active / Retired), versioning, audit logging, and analyst UIs for rule search, detail, history, and contract-to-rule mapping.

4. **Configuration-over-code (Phase 4)**  
   Rule authoring and condition builder UI, conflict validation, and draft simulation so business teams can configure pricing without code deployments.

5. **Safe validation (Phase 5)**  
   Simulation mode, batch simulation, scenario persistence, and a contract testing workbench for onboarding and change validation.

6. **Production scale (Phase 6)**  
   Batch execution, async queues, rule-set caching, and performance telemetry with execution and batch monitoring UIs.

7. **Enterprise platform (Phase 7)**  
   Multi-tenant support, API gateway, versioned pricing services, SLA monitoring, and tenant/service/integration configuration UIs.

---

## Healthcare Pricing Capabilities

- **Methodologies:**** RBRVS, DRG, Flat Rate, Percent of Billed, Per Diem, Anesthesia, Stop Loss.
- **Modifiers:** Applied from reference data (e.g., 26, 50) with correct percentage adjustments.
- **Traceability:** Allowed amount plus contract_id and rule_id for audit and compliance.
- **Rules:** Stored in **PricingRule** and **PricingRuleCondition** with **specificity_score** for best-match behavior.

---

## Retail Recommendation (Future / Portfolio)

- Not in current scope. A future goal is to reuse the same architectural patterns (rules, strategies, API) for a retail recommendation domain to demonstrate cross-domain reuse.
