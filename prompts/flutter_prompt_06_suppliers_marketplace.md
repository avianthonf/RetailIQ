Prompt 06 — Suppliers, Purchase Orders, Goods Receiving, and Marketplace Collaboration

Position: Lead the supplier lifecycle and B2B marketplace experience inside the RetailIQ Flutter application spanning Android and Web. You must translate the entire backend domain defined under `/api/v1/suppliers/*`, `/api/v1/purchase-orders/*`, `/api/v1/goods-receipts/*`, `/api/v1/marketplace/*`, `/api/v1/rfqs/*`, `/api/v1/quotes/*`, `/api/v1/supplier-dashboard/*`, and `/api/v1/documents/*` into precise UX flows, service layers, and state machines. Use the OpenAPI spec to capture every request/response schema, role requirement, pagination pattern, and webhook handshake.

Functional Pillars
1. Supplier Directory & CRM
   - Build searchable directory surfaces with filters on status, rating, lead time, regions, payment terms. Provide results virtualization + summary cards mapping to supplier profile schema (`SupplierProfile` model). Include quick actions (view catalog, start RFQ, open chat) gated by role.
   - Provide supplier detail view with tabs: Overview, Catalog, Performance, Documents, Contacts. Pull metrics from `/api/v1/suppliers/{id}/metrics` and show time-series charts.
2. Purchase Order Lifecycle
   - Architect PO board segmented by states (Draft, Awaiting Approval, Sent, Partially Received, Closed, Cancelled). Data pulled from `/api/v1/purchase-orders?status=` with cursor pagination.
   - Implement PO creation wizard referencing request schema (supplier, ship-to store, line items, pricing, taxes, payment milestones). Support template duplication, currency conversion, attachments, approval routing with `/api/v1/purchase-orders/{id}/approve`.
   - Provide timeline view (events feed) merging backend audit trail.
3. Goods Receipts & Quality Control
   - Build receiving workbench tied to PO lines. Support scanning, partial receipts, damages. Sync with `/api/v1/goods-receipts` and `POST /api/v1/goods-receipts/{id}/items` endpoints. Show tolerance thresholds, auto-create stock adjustments, trigger alerts for discrepancies.
   - Provide photo capture + annotation for quality issues. Upload via `/uploads` endpoint and link to GRN.
4. Marketplace RFQs & Negotiations
   - RFQ composer enabling multi-supplier broadcast, attachments, deadline, target price. Submit via `/api/v1/rfqs` and manage responses list with timeline.
   - Quote comparison matrix pulling `/api/v1/quotes` with scoring (price, lead time, payment terms). Provide acceptance flow issuing marketplace PO via `/api/v1/marketplace/purchase-orders`.
   - Integrate messaging or comment threads referencing `/api/v1/marketplace/messages` (if defined) or fallback instructions for email.
5. Supplier Dashboard (Supplier Role Web Portal)
   - Dedicated layout for supplier role showing pipeline metrics, open RFQs, performance KPIs, compliance tasks. Use same Flutter codebase with role-based route gating.

Architecture Requirements
- Modules: `features/suppliers`, `features/purchase_orders`, `features/marketplace`. Each exposes repository (Dio + caching), service layer (domain commands), presentation (Riverpod Notifier + UI).
- Provide offline drafts for POs and RFQs stored locally with sync queue when online. Document conflict resolution.
- Implement WebSocket/SSE subscription for RFQ updates, PO status changes. Outline channel naming and reconnection policy.
- Enforce granular permissions per role (owner, buyer, supplier). Expose `SupplierCapability` model from backend to dynamically show actions.

UI & UX
- Desktop: Kanban boards, split panes, multi-column tables with sticky headers. Mobile: stacked cards with action sheets. Tablet: two-column with collapsible timeline.
- Provide mass upload (CSV) for catalog updates. Show validation errors referencing backend error schema.
- Offer analytics overlays: supplier scorecards, fill-rate trends, lead-time heat maps. Use `syncfusion_flutter_charts` or `charts_flutter` as specified.
- Provide document viewer for PO PDFs, COA, compliance certificates using `flutter_pdfview` or platform view on web.

Testing & Telemetry
- Unit tests for DTO mapping, offline queue, permission gating.
- Integration tests for PO wizard, RFQ broadcast, goods receipt submission.
- Instrument analytics (supplier_viewed, po_created, rfq_sent, quote_accepted) referencing event payload spec.

Deliverable: Output file/folder plan, provider diagram, widget tree sketches, state charts, offline sync pseudo-code, REST/WebSocket contracts, and sample payloads for key flows. Ensure every endpoint reference matches OpenAPI path exactly and note required headers (auth, store, correlation IDs).
