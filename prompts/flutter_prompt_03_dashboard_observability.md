Prompt 03 — Cross-Platform Executive Dashboard & Observability Surfaces

Mission: You helm the dashboard and observability feature set for the RetailIQ Flutter app. Architect a multi-surface experience that aggregates metrics from `/api/v1/dashboard/*`, `/api/v1/alerts/*`, `/api/v1/market-intelligence/*`, `/api/v1/observability/*`, `/api/v1/ops/maintenance`, and WebSocket feeds defined under `market_intelligence.stream`. Your output must describe every widget, data contract, and responsive behavior for both Android and Web, across mobile/tablet/desktop breakpoints.

Scope
1. Dashboard Overview
   - Build hero KPI tiles (Sales Today, Gross Margin, Inventory at Risk, Outstanding POs, Loyalty Redemptions) using `/api/v1/dashboard/overview` response schema. Include sparkline micro-charts using `fl_chart` or `syncfusion_flutter_charts` with streaming updates.
   - Provide `Forecast Horizon` panel merging `/api/v1/forecasting/store` + `/api/v1/forecasting/sku`. Explain caching strategy (Redis TTLs) and local fallback store.
   - Add `Live Signals` lane fed by WebSocket (market intelligence + notifications). Outline channel subscription protocol, reconnection policy, and offline queueing.
2. Alerts & Incidents
   - Implement alerts inbox referencing `/api/v1/alerts/feed` (pagination, severity, ack endpoint). Support multi-select, bulk resolve, and role-based assignments. Document state diagram.
   - Provide incident timeline overlay pulling `/api/v1/observability/incidents` + linking out to Grafana deep links provided in payload metadata.
3. Observability Control Room
   - Desktop split-pane with charts for latency, error rate, throughput (Prometheus proxy endpoints in spec). Provide toggles for timeframe, environment, percentile capturing.
   - Integrate `MaintenanceBanner` sourced from `/api/v1/ops/maintenance` with CTA to view planned downtime doc.
   - Offer log stream viewer (tail) hitting `/api/v1/observability/logs?follow=1` via SSE on web, WebSocket fallback on mobile.
4. Personalization & Layout
   - Persist dashboard layout preferences in `/api/v1/users/{id}/preferences`. Provide drag-and-drop grid editing on desktop using `ReorderableSliverGrid`, simplified stacked list on mobile.
   - Implement theming per user preference (light/dark/high contrast). Document interplay with global theme system defined in Prompt 01.

Interaction Design
- Provide skeleton states, empty states, and error boundaries for each widget.
- Document gestures: pinch-to-zoom for charts, keyboard shortcuts on web, accessible focus order.
- Add share/export actions for KPI cards (PNG/PDF export, share sheet, clipboard for web). Ensure fiber friendly asynchronous operations.

Tech
- Use Riverpod providers per data stream with `AutoDispose` for short-lived feeds. Define caching policy per endpoint (stale-while-revalidate, TTL 60s for overview, 5s for live signals).
- Enumerate DTOs for dashboard responses, linking each to OpenAPI schema references.
- Provide integration test outline verifying data merges, pagination, WebSocket resilience.

Deliverables
- Detailed widget tree diagrams for phone/tablet/desktop.
- State charts for alert handling & signal subscription.
- List of metrics with exact API fields and example payloads.
- Performance considerations (frame budget, background isolates for heavy parsing).

Output should enumerate files, classes, provider setup, and blueprint for telemetry instrumentation (analytics events when users expand/collapse tiles).
