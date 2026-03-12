Prompt 10 — Settings, Access Control, Notifications, Offline Sync, and Platform Services

Role: As the senior platform engineer, define the comprehensive Settings & Platform Services domain for the RetailIQ Flutter application (Android + Web). This includes user/profile settings, role & permission management, webhooks, developer keys, notifications, offline sync controls, localization, theme/accessibility preferences, device management, and observability connectors. Use the OpenAPI spec sections `/api/v1/users/*`, `/api/v1/settings/*`, `/api/v1/access-control/*`, `/api/v1/roles/*`, `/api/v1/webhooks/*`, `/api/v1/developer/*`, `/api/v1/notifications/*`, `/api/v1/devices/*`, `/api/v1/localization/*`, `/api/v1/preferences/*`, `/api/v1/ops/*`, and `/api/v1/observability/*` to derive payloads, validation, and error flows.

Functional Areas
1. User & Profile Settings
   - Build profile editor referencing `/api/v1/users/me` with avatar upload, contact info, notification preferences, MFA toggles. Provide device list (sessions) via `/api/v1/devices` with revoke action.
   - Implement password change, security questions, biometric opt-in/out. Ensure step-up auth with OTP before sensitive changes.
2. Role-Based Access Control
   - Render role matrix using `/api/v1/roles` + `/api/v1/access-control/policies`. Provide CRUD UI for custom roles (permissions toggles grouped by module). Enforce owner-only creation, staff-limited editing. Validate payloads per spec and show diff before publishing.
   - Provide user assignment flow hitting `/api/v1/access-control/assignments`. Surface audit history linking to `/api/v1/access-control/audit`.
3. Webhooks & Developer Integrations
   - Webhook management: list endpoints, create/edit with secret rotation, signature preview, retry logs referencing `/api/v1/webhooks/*`. Provide delivery log viewer with filtering and JSON inspector. Offer test delivery UI hitting `/api/v1/webhooks/test`.
   - Developer keys & OAuth clients: surfaces built on `/api/v1/developer/apps`, `/api/v1/developer/keys`, `/api/v1/developer/oauth`. Provide regenerate, disable, metadata edit flows. Show usage metrics and rate limit status.
4. Notifications & Preferences
   - Notification center with categories (alerts, finance, marketplace). Fetch from `/api/v1/notifications/feed`, support mark read, snooze, mute. Provide preference matrix per channel (push, email, SMS, WhatsApp) saved via `/api/v1/preferences/notifications`.
   - Integrate push infrastructure (Firebase Cloud Messaging / Web Push). Document token registration flow hitting `/api/v1/notifications/register-device`.
5. Offline Sync & Device Policies
   - Build offline mode settings: data retention duration, storage usage, selective module sync. Use `/api/v1/settings/offline` endpoints. Provide per-device overrides and diagnostics (last sync timestamp, queue depth).
   - Expose conflict resolution logs referencing `/api/v1/sync/conflicts` with ability to reconcile manually.
6. Localization, Theme, Accessibility
   - Manage available locales via `/api/v1/localization/locales`. Provide download/update flow for ARB bundles. Offer theme presets (brand, high contrast) and custom color overrides saved via `/api/v1/preferences/theme`.
   - Accessibility controls: font scale, reduced motion, screen reader hints. Persist via preferences endpoints.
7. Observability Connectors & Ops
   - Provide panels for webhook to ops tools (PagerDuty, Slack) hitting `/api/v1/observability/connectors`. Support API key input, validation, and incident routing rules.
   - Surface maintenance mode toggle (owner-only) referencing `/api/v1/ops/maintenance`. Provide preview of downtime message and scheduling UI.

Architecture & Implementation
- Modules: `features/settings`, `features/access_control`, `features/webhooks`, `features/developer`, `features/notifications`, `features/offline`, `features/localization`, `features/observability`.
- Each module exposes repository (Dio with interceptors), domain services (validators, diff engine), and presentation controllers (Riverpod/Bloc). Document dependency graph and cross-module communication (e.g., notifications referencing settings preferences).
- Provide `SettingsRouter` under `/settings/*` routes as defined in Prompt 01 with nested navigation (tabs on desktop, bottom sheet on mobile). Describe guard conditions per role.
- Outline offline cache usage (Hive encrypted boxes) for preferences, localization bundles. Provide migration strategy on schema changes.
- Implement universal forms framework with reusable validators derived from OpenAPI (lengths, regex). Include unsaved changes guard.

UX & Interaction
- Responsive layout: desktop uses tabs + split panes; tablet uses side rail + detail; mobile uses nested pages. Provide breadcrumbs and search inside settings.
- Provide audit log viewer across modules, referencing `/api/v1/audit` endpoints. Include filters by user, action, module.
- Ensure confirmation dialogs for destructive actions, inline success/error toasts, loading indicators. Show last updated timestamp per section.
- Document accessibility: keyboard navigation, focus order, ARIA roles for form inputs on web, semantics for screen readers on mobile.

Testing & Telemetry
- Unit tests for validators, diff builders, offline preference store.
- Integration tests mocking backend for role creation, webhook test delivery, device revocation, maintenance toggle.
- Analytics instrumentation: `role_created`, `webhook_saved`, `notification_preference_updated`, `offline_sync_configured`.

Deliverable: Provide file tree, provider/state diagrams, detailed widget hierarchies, REST contract tables per area, offline sync pseudo-code, and instructions for instrumentation + settings migration. Reference exact API paths, headers, request/response schemas from the OpenAPI spec to ensure precision.
