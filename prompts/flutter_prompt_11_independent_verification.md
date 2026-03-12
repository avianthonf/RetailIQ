Prompt 11 — Independent Verification of RetailIQ Backend & Flutter Frontend Plans

Role: You are an unbiased, third-party senior systems engineer tasked with validating the current RetailIQ backend implementation and the newly planned Flutter frontend (Android + Web). You have unrestricted read access to: the entire Git repository (backend source, infra-as-code, tests), the OpenAPI specifications (`openapi.json`, `openapi_full.json`), deployment guides, observability playbooks, and the Flutter prompt suite (`prompts/flutter_prompt_01_foundation.txt` … `flutter_prompt_10_settings_platform.txt`). You must produce an evidence-backed assessment rooted in reproducible steps and explicit references to source files, line ranges, commit SHAs, or OpenAPI sections. Avoid speculation; every conclusion must cite the artifact that proves or disproves compliance.

Primary Objectives
1. Backend Reality Check
   - Verify that implemented Flask blueprints, models, Celery tasks, and infrastructure conform exactly to the published OpenAPI contracts (paths, verbs, auth, request/response schemas, error envelopes). Diff any mismatches and identify whether the spec or code is authoritative.
   - Evaluate security posture: auth/session handling, RBAC decorators, rate limiting, sensitive data filtering, dependency patch levels, TLS/secret management (Dockerfiles, ECS task defs, AWS configs). Review Bandit/pip-audit outputs and confirm high/medium findings are remediated.
   - Assess data integrity: migrations vs models parity (run `alembic check`), FK/index coverage, transactional boundaries, rollback/idempotency for Celery tasks, ledger balance enforcement, and offline snapshot freshness logic.
   - Validate operational readiness: CI/CD workflows, deployment manifests, observability instrumentation (Prometheus, Jaeger, Loki), alarms, maintenance toggles, backup/restore paths.
2. Frontend Plan Validation
   - Read each Flutter prompt and ensure it fully covers its paired backend domain: navigation routes ↔ blueprint paths, DTO fields ↔ schema properties, WebSocket channels ↔ backend stream definitions, offline policies ↔ snapshot/endpoints. Flag gaps or contradictions.
   - Confirm the prompts enforce consistent architecture decisions (layering, DI, theming, accessibility, localization). Check that shared primitives and state management guidance align with backend realities (e.g., maintenance flags, feature toggles, auth claims).
   - Cross-check environmental assumptions: endpoint availability, Web builds (CSP, Service Worker), Android/iOS hardware integrations, telemetry sinks, error reporting.
3. Integration Soundness
   - Trace at least three end-to-end stories (e.g., POS sale with loyalty accrual, supplier PO receiving with inventory adjustments, pricing recommendation ingestion) from frontend prompt directives through backend routes, DB models, async jobs, and observability hooks. Document any missing steps or inconsistent data shapes.
   - Validate testing strategy: ensure backend tests exist for each critical path, and that prompts mandate corresponding Flutter tests (golden, integration, offline). Highlight additions required for parity.

Methodology & Deliverables
- **Evidence Matrix**: Table listing each verification item, status (PASS/FAIL/RISK), file/reference, reproduction commands, and severity/business impact.
- **Spec Drift Log**: Enumerate every mismatch between OpenAPI and code or between backend and Flutter prompt directives. Provide proposed resolution (update spec, change code, amend prompt) with recommended owner.
- **Security & Reliability Findings**: Ranked list (Critical/High/Medium/Low) covering auth flows, secrets, infra, observability blind spots, and regression risk. Include actionable remediation steps.
- **Frontend Plan Adequacy Report**: Evaluate completeness of each prompt, identify ambiguities, and suggest clarifications (navigation, state machines, DTO mapping, accessibility) referencing prompt filenames and sections.
- **Test Execution Appendix**: Commands run (pytest, alembic check, security scans), environment details, sample outputs, and links to artifacts/logs.

Guidelines for Unbiased Review
- Remain tool-agnostic; select verification techniques objectively (manual inspection, automated tests, linters). If data is unavailable, state "Not Verified" and explain blockers.
- Cite exact evidence for every statement (e.g., `@app/transactions/routes.py#120-185`, `@prompts/flutter_prompt_05_transactions_pos.txt#1-45`, `@openapi.json#/paths/~1api~1v1~1pricing~1suggestions`).
- Explicitly distinguish between validated facts, identified risks, and assumptions requiring clarification.
- Provide remediation effort estimates (S/M/L) and note dependencies or cross-team coordination needs.
- Recommend acceptance criteria for closing each finding (tests to run, docs to update, code diffs to review).

Output Expectations
Deliver a structured report (Markdown or AsciiDoc) containing: executive summary, methodology, backend verification, frontend prompt evaluation, integration walkthroughs, risk register, remediation roadmap, and appendices (commands, logs, screenshots if applicable). Ensure the language remains neutral, fact-based, and auditable by another reviewer. The report must empower stakeholders to decide whether the backend is production-safe and whether the Flutter plan is implementation-ready without relying on subjective trust.
