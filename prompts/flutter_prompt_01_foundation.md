Prompt 01 — RetailIQ Flutter Foundation, Shell, and Navigation

You are the lead Flutter architect responsible for producing the complete shell of the RetailIQ cross-platform application (Android + Web). You have full read access to the RetailIQ backend OpenAPI specification (`openapi.json`) and may inspect every schema, response example, authentication header, pagination contract, webhook definition, and error envelope. Use that specification to wire every navigation entry and service stub to its canonical endpoint path.

Goals
1. Emit a production-ready Flutter 3.16+ project using Dart 3, Material 3, and `flutter_web_plugins` so the same codebase compiles for Android, Chrome, Edge, and Safari.
2. Enforce a layered architecture: `app/` (routes + boot), `core/` (theme, typography, localization, feature toggles), `data/` (REST clients, DTOs generated from OpenAPI, offline caches), `domain/` (use cases with pure Dart logic), `features/<module>/presentation` (widgets + state machines).
3. Define a navigation scaffold matching the backend domain areas: Auth, Dashboard, Inventory, Transactions/POS, Suppliers & Marketplace, Pricing/Forecasting, Loyalty & Finance, Analytics & Intelligence, Settings/Observability.
4. Embed guardrails for screen size breakpoints (phone <600dp, tablet <1024dp, desktop >=1024dp). Ensure the router renders adaptive layouts (navigation rail vs drawer vs persistent side bar) per width class.
5. Configure environment selection (prod/stage/local) via flavors, `.env` loader, and sealed `BackendEnvironment` class that carries the base URL, WebSocket endpoints, and CDN asset host.

Deliverables & Constraints
- Generate `main.dart` that reads secure storage for tokens, bootstraps dependency injection (Riverpod or Bloc + get_it), wires a guarded `GoRouter` (or `Routemaster`) tree, and redirects unauthenticated users to the OTP/login flow.
- Provide a `ThemeFactory` that maps RetailIQ brand tokens (primary=#1E4BD1, secondary=#27C6AD, accent=#FFB347, error=#F04438, background gradient from #030711 to #0F172A). Typography should use `Space Grotesk` for headings and `IBM Plex Sans` for body/monospace metrics.
- Bake dark-mode and high-contrast toggles with persistence in `SharedPreferences`/`localStorage`. Respect platform brightness listeners.
- Insert an `AppBootstrap` widget that initializes: logging (Firebase Crashlytics + Sentry DSN placeholders), feature flags (remote config stub), analytics sink (segment events), and HTTP client (Dio) with interceptors for auth headers, request IDs, request timeline logging, and automatic retries for idempotent verbs.
- Define shared layout primitives: `RetailScaffold`, `RetailNavigationRail`, `RetailAppBar`, `RetailSplitPane`, `MetricTile`, `AsyncStateView`.
- Wire Web entry via `index.html` to load fonts, register a Service Worker (PWA offline bootstrap), and set CSP for the API host.

Router Blueprint (ensure exact route constants)
- `/auth/welcome`, `/auth/register`, `/auth/verify-otp`, `/auth/login`, `/auth/forgot-password`.
- `/dashboard/overview`, `/dashboard/alerts`, `/dashboard/live-signals`.
- `/inventory/products`, `/inventory/stock-audits`, `/inventory/receiving`, `/inventory/transfers`.
- `/transactions/pos`, `/transactions/history`, `/transactions/returns`, `/transactions/invoices`.
- `/suppliers/directory`, `/suppliers/purchase-orders`, `/suppliers/goods-receipts`, `/marketplace/rfqs`, `/marketplace/quotes`.
- `/pricing/strategies`, `/pricing/market-intel`, `/forecasting/sku`, `/forecasting/store`.
- `/loyalty/programs`, `/loyalty/accounts`, `/finance/ledger`, `/finance/loans`, `/finance/treasury`.
- `/analytics/revenue`, `/analytics/inventory`, `/analytics/customer`, `/analytics/events`, `/ai/vision`, `/ai/nlp`.
- `/settings/profile`, `/settings/access-control`, `/settings/webhooks`, `/settings/observability`.

Implementation Requirements
- Declare strongly typed navigation records (`AppRoute`) carrying: path, icon data, label, role requirement, and `FeatureFlag` gates. Provide a `RoleAwareMenuBuilder` that filters the tree based on the authenticated user (`owner`, `staff`, `supplier`, `developer`).
- Implement skeleton screens with shimmering placeholders while data loads. Use `Sliver`-based scroll regions for dashboards.
- Provide global error surfaces: toast for recoverable errors, full-page `FailureState` with CTA for fatal network issues, and `MaintenanceBanner` triggered by `/api/v1/ops/maintenance` flag.
- Implement localization scaffolding for `en`, `hi`, and `es`. Store strings in ARB files and ensure RTL safety.
- Document in-code (doc comments) the link between each route and the OpenAPI tag(s) it binds to.
- Ensure tests cover: router guards, theme toggles, environment switching, and serialization of persisted nav state.

Testing & Tooling
- Configure `melos` or `very_good_cli` for mono-repo style management.
- Add `golden_toolkit` for rendering the shell at multiple breakpoints.
- Lint via `flutter_lints` + `very_good_analysis`. No TODOs left unaddressed.

Output
Return the full source structure with highlighted files, key widgets, and explanations of how each route wires to the backend. Provide runnable instructions (`flutter run -d chrome` / `flutter build apk`).
