Prompt 05 — Transactions, POS, Billing, and Returns Suite

Context: Design the entire Transactions/POS vertical for the RetailIQ Flutter application, ensuring seamless omnichannel checkout on Android tablets, ruggedized handhelds, and desktop-class web browsers. You have full access to the RetailIQ OpenAPI spec for `/api/v1/transactions/*`, `/api/v1/pos/*`, `/api/v1/returns/*`, `/api/v1/invoices/*`, `/api/v1/payments/*`, `/api/v1/customers/*`, `/api/v1/receipts/*`, and `/api/v1/loyalty/*`. Use exact schemas, enums, and status codes to define data models, error handling, and offline fallbacks.

Mandates
1. POS Shell
   - Architect a composable POS workspace with modular panes: cart builder, product search, customer panel, payment rail, and loyalty/promotions summary. Provide adaptive layout rules (phone stacked sheets, tablet split view, desktop tri-column). 
   - Integrate scanning (camera, hardware scanner, manual SKU entry) hitting `/api/v1/products/search`. Provide debounce, result caching, and offline fallback from local inventory cache.
   - Support quick actions: discount, custom item, gift card, notes, suspend/resume cart.
2. Checkout + Payments
   - Implement tender orchestration referencing `/api/v1/payments/checkout` (cash, card, UPI, wallet, split payments). Outline UI states for tip entry, surcharge, currency conversions.
   - Add payment hardware abstraction (Android intent for UPI, web Payment Request API). Provide fallback manual entry. Capture signature or PIN as required.
   - Ensure compliance with backend validations: totals rounding, tax lines, GST breakdown, digital receipt toggles.
3. Customer 360
   - Embed customer lookup `/api/v1/customers/search`, enrollment, and loyalty balance retrieval. Display purchase history, outstanding credit, and targeted offers (driven by `/api/v1/decisions/offers`).
   - Provide inline enrollment forms with address, GSTIN, tags, preferences.
4. Returns & Exchanges
   - Build returns workflow referencing `/api/v1/returns`. Support full/partial, receipt lookup via barcode scan, reason codes, quality checks, refund to tender logic. Provide restocking/cost adjustments via `/api/v1/stock-adjustments` integration.
   - Add exchange/resell flow: convert return to cart credit, apply to new items, finalize sale.
5. Invoices & Receipt Printing
   - Generate invoice preview referencing `/api/v1/invoices/{id}` and receipt template metadata from `/api/v1/receipts/templates`. Provide PDF export, print, and email.
   - Support asynchronous print jobs via `/api/v1/receipts/print-jobs`. Document polling/backoff.

Architecture & State
- Use Bloc or StateNotifier per workflow: `CartBloc`, `PaymentBloc`, `CustomerBloc`, `ReturnBloc`. Define events/states, optimistic updates, rollback on error.
- Provide `TransactionRepository` layering Dio client, caching, and offline queue for carts when network unavailable (persist to Hive/Isar). Document reconciliation algorithm.
- Implement comprehensive validation: price overrides require manager PIN, voids require reason logging, high-value alerts from `/api/v1/alerts`.

UX & Accessibility
- Provide keyboard-first shortcuts on web (scan enters search, F2 add customer, F12 pay). On mobile, expose bottom sheet quick actions.
- Build tactile feedback (haptics) for key actions. Provide color-coded lines for item status (discounted, returned, out-of-stock).
- Ensure large tap targets, focus trapping in modals, screen reader labels for totals, dynamic currency text for INR/other locales.

Data + Telemetry
- Enumerate DTOs for cart line, promotion, tender, loyalty. Map to OpenAPI refs.
- Emit analytics events (checkout_started, payment_captured, return_processed) with payload keys.
- Provide integration tests mocking Dio: scanning, loyalty accrual, split payment failure.

Deliverable: Outline files (`features/transactions/presentation/...` etc.), widget tree diagrams, Bloc state charts, offline queue pseudo-code, and example request/response pairs for each critical endpoint. Ensure instructions mention concurrency handling, error surfaces, and resilience for both Android and Web deployments.
