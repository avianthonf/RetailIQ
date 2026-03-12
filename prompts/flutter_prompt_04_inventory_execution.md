Prompt 04 — Inventory, Stock Integrity, and Receiving Workflows

Role: You are the principal engineer in charge of all inventory-facing functionality inside the RetailIQ Flutter app (Android + Web). Architect exhaustive flows for product catalog management, stock audits, stock transfers, goods receiving, barcode registry, and offline resilience. Use the RetailIQ OpenAPI spec sections for `/api/v1/inventory/*`, `/api/v1/products/*`, `/api/v1/stock-adjustments/*`, `/api/v1/stock-audits/*`, `/api/v1/receiving/*`, `/api/v1/barcodes/*`, `/api/v1/transfers/*`, and `/api/v1/receipts/*` to derive DTOs, pagination schemes, validation rules, and error codes.

Functional Scope
1. Product Catalog
   - Design list + detail views with virtualized tables on web and Masonry cards on mobile. Include search, filters (category, supplier, stock status), and bulk edit actions (price, tax, tags) tied to the `PATCH /api/v1/products/bulk` endpoint.
   - Provide create/edit forms referencing `POST /api/v1/products` schema (name, SKU, barcode, HSN, GST slabs, lead time). Include image uploader (camera/gallery/web drag-drop) storing metadata before calling `/uploads` endpoint.
2. Stock Adjustments & Audits
   - Build guided adjustment workflow referencing `POST /api/v1/stock-adjustments`. Include reason codes, multi-line item entry, and immediate feedback on inventory ledger impact.
   - Architect stock audit jobs: create audit, barcode scanning via camera (mobile) or scanner input (web), offline capture when connectivity drops, and sync via `/api/v1/stock-audits/{id}/items`.
   - Provide discrepancy visualization and export.
3. Goods Receiving + Purchase Order Integration
   - Render purchase orders fetched from `/api/v1/purchase-orders`. Provide status chips, expected delivery, and `Receive Now` CTA launching a receiving wizard.
   - Receiving wizard must support: scan/enter item, capture lot/batch, expiry date, input quantity received/damaged, attach GRN docs, finalize via `POST /api/v1/goods-receipts`.
   - Sync adjustments to inventory ledger and show success summary referencing backend response fields.
4. Transfers & Barcode Registry
   - Multi-store transfer initiation, approval, and fulfillment via `/api/v1/transfers`. Explain cross-store permission checks.
   - Barcode registry maintenance (bulk import CSV, manual entry). Link to receipt template module for POS printing alignment.

Architecture & State
- Define `InventoryRepository` interfacing with Dio and caching (Hive for offline). Provide `InventorySyncService` reconciling offline operations (audits, adjustments) via queue.
- Use Bloc/Riverpod states per sub-module (CatalogCubit, AdjustmentCubit, AuditCubit). Document state transitions.
- Provide data tables with virtualization (e.g., `SyncfusionDataGrid`) for tens of thousands of products. Outline pagination design aligned with backend `cursor`/`limit` parameters.

UX Details
- Responsive layouts: phone list -> detail sheet; tablet uses split view; desktop uses three-pane (filters, table, preview).
- Provide inline analytics: reorder suggestions from `/api/v1/forecasting/sku` embedded in product detail.
- Add scanning overlays using ML Kit or barcode_web library; degrade to manual entry.
- Support undo/redo for adjustments before submission.
- Show permission gating (staff vs owner). Non-authorized actions show disabled CTA with tooltip referencing `403` reason from spec.

Testing & Telemetry
- Unit tests for DTO mapping, offline queue reconciliation, scanning pipeline.
- Integration tests mocking backend for adjustment submission, PO receiving, barcode creation.
- Instrument analytics events (product_created, audit_started, transfer_initiated) with payload definitions.

Deliverable: Provide file/module map, widget tree per feature, state diagrams, offline sync algorithm pseudo-code, and example API payloads from the spec to ensure exhaustive guidance.
