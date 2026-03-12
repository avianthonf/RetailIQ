Prompt 07 — Pricing Engine, Forecasting Studio, and Market Intelligence Surfaces

Responsibility: Define the entire Pricing & Forecasting experience for the RetailIQ Flutter application across Android and Web. Use the OpenAPI spec sections `/api/v1/pricing/*`, `/api/v1/forecasting/*`, `/api/v1/market-intelligence/*`, `/api/v1/alerts/*`, `/api/v1/events/*`, and `/api/v1/decisions/*` to capture exact payloads, enums, and correlations. The module must let owners and analysts configure pricing rules, inspect elasticity models, review competitive signals, and run forecast simulations for stores/SKUs.

Feature Streams
1. Pricing Strategy Workbench
   - Provide listing of pricing policies (competitive guardrails, margin floors, promo overrides) by hitting `/api/v1/pricing/strategies`. Show status, owner, rule count, last evaluation.
   - Build detail editor using schema (conditions, triggers, actions). Support multi-step forms with validation referencing backend enums (`PRICE_INCREASE`, `PRICE_DECREASE`, `LOCK_PRICE`, etc.). Include simulation panel calling `/api/v1/pricing/simulate` with scenario inputs and showing expected KPIs.
   - Expose audit trail for rule changes via `/api/v1/pricing/history`. Provide diff viewer.
2. Elasticity & Recommendation Console
   - Render SKU-level elasticity models from `/api/v1/pricing/elasticity`. Use charts (confidence bands, break-even). Provide toggles to overlay actual sales vs predicted.
   - Show recommendation feed from `/api/v1/pricing/recommendations` with filters (store, category, action type). Provide Accept/Reject actions posting to `/api/v1/pricing/recommendations/{id}` with `decision` payload.
3. Forecasting Studio
   - Multi-sku timeline comparing Prophet, XGBoost, LSTM outputs provided via `/api/v1/forecasting/sku` and `/api/v1/forecasting/store`. Provide horizon selection, seasonality toggles, anomaly markers from `/api/v1/forecasting/anomalies`.
   - Build scenario builder: user adjusts promotion calendar, supply constraints, and sends to `/api/v1/forecasting/scenario`. Render results + delta vs baseline.
   - Outline caching and offline fallback (store last 30 days forecasts locally). Describe background refresh tasks.
4. Market Intelligence Command Center
   - Visualize live indices from `/api/v1/market-intelligence/signals` (Fisher, Laspeyres, competitor price drift). Use WebSocket stream for near-real-time updates. Document channel names, authentication headers, reconnection with exponential backoff.
   - Provide anomaly review queue referencing `/api/v1/market-intelligence/anomalies`. Show details (supplier, SKU, deviation %) with resolution workflow posting decisions.
   - Integrate `Event Calendar` using `/api/v1/events/calendar` to overlay festivals, weather, and campaigns on charts.

Architecture & State
- Modules: `features/pricing`, `features/forecasting`, `features/market_intel`. Each with repository (Dio + caching), domain use cases, presentation (Riverpod or Bloc). Document provider relationships and dependency graph.
- Introduce `AnalyticsSampler` isolate to process large time-series before painting to avoid jank.
- Provide advanced data table components for desktop (sticky columns, pivot). For mobile, degrade to paginated cards.

UX/Interaction
- Support breakpoints with multi-pane layout on desktop: navigation rail -> filter panel -> chart canvas -> detail drawer. On mobile, use nested navigation stack.
- Provide scenario timeline with drag markers, keyboard shortcuts, and accessible descriptions.
- Integrate inline explanations referencing backend metadata (`insight_text`, `confidence_score`).
- Offer export (CSV, PDF) hitting `/api/v1/pricing/export` and `/api/v1/forecasting/export` endpoints. Provide progress indicator for long-running exports with SSE status updates.

Testing & Telemetry
- Outline golden tests for charts at key breakpoints.
- Integration tests mocking Dio for strategy CRUD, forecast scenario, WebSocket reconnection.
- Analytics events: `pricing_rule_updated`, `recommendation_accepted`, `forecast_scenario_run`, `market_signal_subscribed`.

Deliverable: Provide file tree, detailed widget hierarchies, state diagrams, data contract tables referencing OpenAPI schema names, caching/offline strategies, and WebSocket protocol summary. Ensure instructions mention concurrency handling, error fallback UI, and instrumentation hooks for diagnostics.
