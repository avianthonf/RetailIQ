Prompt 08 — Loyalty, Credit Ledger, Embedded Finance, and Treasury Suite

Assignment: Architect the Loyalty & Embedded Finance vertical for the RetailIQ Flutter application, unifying loyalty programs, credit ledger, lending, treasury sweeps, insurance, and customer financing tools across Android and Web. Use the OpenAPI spec covering `/api/v1/loyalty/*`, `/api/v1/credit/*`, `/api/v1/finance/*`, `/api/v2/finance/*`, `/api/v1/ledger/*`, `/api/v1/loans/*`, `/api/v1/treasury/*`, `/api/v1/insurance/*`, and `/api/v1/customers/*`. Reference precise schemas, enums, and error codes from the spec.

Feature Domains
1. Loyalty Program Administration
   - Multi-program listing with filters (active, upcoming, expired). Show KPIs (members, points issued, redemption rate) from `/api/v1/loyalty/programs`.
   - Program editor referencing request schema (points per rupee, redemption rate, expiry days, tiers, benefits). Provide real-time preview of customer-facing copy.
   - Configure automation rules (birthday bonus, inactivity expiry) hitting `/api/v1/loyalty/automation` endpoints.
2. Customer Loyalty Accounts
   - Searchable ledger per customer via `/api/v1/loyalty/accounts` with timeline of transactions (EARN/REDEEM/EXPIRE/ADJUST). Provide statements export.
   - Integrate with POS (Prompt 05) to show loyalty balance and redemption options.
   - Implement points adjustment workflow requiring manager approval (OTP or PIN) referencing `/api/v1/loyalty/adjust`.
3. Credit Ledger & Embedded Finance
   - Display credit ledger entries per customer/store via `/api/v1/credit/ledger`. Provide filters, search, and double-entry visualization referencing backend ledger schema.
   - Build loan application flow hitting `/api/v1/loans/apply` and `/api/v1/loans/{id}` for status updates. Include eligibility checks (credit score, turnover) from `/api/v1/finance/credit-profile`.
   - Show repayment schedules, auto-debit settings, delinquency alerts from `/api/v1/loans/repayments` and `/api/v1/alerts`.
4. Treasury & Yield Management
   - Configure sweep strategies via `/api/v1/treasury/sweep-config`. Provide UI for thresholds, allocation, yield curves. Display performance analytics referencing `/api/v1/treasury/performance`.
   - Provide cash management console with liquidity buckets, inflow/outflow charts.
5. Insurance & Risk Products
   - Enrollment wizard for parametric insurance via `/api/v1/insurance/policies`. Include triggers (weather, power outage), coverage sums, premium schedule.
   - Claims dashboard referencing `/api/v1/insurance/claims` with timelines and document uploads.

Architecture & Data
- Modules: `features/loyalty`, `features/finance`, `features/credit`, `features/treasury`, `features/insurance` built with repositories, domain services, and presentation layers.
- Provide `LedgerEngine` class mapping backend double-entry payload to UI aggregates.
- Define caching strategy (Hive) for loyalty accounts and loan schedules for offline viewing. Ensure encryption at rest.
- Outline state management (Riverpod/Bloc) for program editor, ledger viewer, loan application wizard, treasury config.

UX Considerations
- Responsive layouts with data-dense tables on desktop (sticky columns, inline filters) and stacked cards on mobile.
- Provide timeline visualizations for ledger transactions, repayment schedules, treasury sweeps. Use `charts_flutter` or `syncfusion_flutter_charts`.
- Include callouts for compliance info (GST, KYC). Link to documents via `/api/v1/documents`.
- Provide notifications, tasks, and reminders (e.g., loan payment due) integrating `/api/v1/alerts` and push notification scaffolding.

Security & Compliance
- Enforce role-based access (owner, finance manager). Sensitive actions require step-up auth (biometric/PIN).
- Mask sensitive info when screen recording flag is on (Android privacy callbacks). On web, offer privacy mode.
- Log all finance interactions for audit analytics events.

Testing & Telemetry
- Unit tests for ledger math, program validations, loan workflow. Integration tests mocking backend for sweep config and insurance claims.
- Instrument analytics events: `loyalty_program_created`, `loan_applied`, `treasury_sweep_updated`, `insurance_claim_submitted`.

Deliverable: Provide file structure, widget trees, state diagrams, ledger transformation pseudo-code, sample API payload tables, and offline sync strategy documentation. Reference exact endpoints, headers, request fields, and response schemas from the OpenAPI spec.
