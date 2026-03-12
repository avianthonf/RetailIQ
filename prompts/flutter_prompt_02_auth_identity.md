Prompt 02 — Unified Auth, Identity, and Access Control Experience

Role: You are the authentication domain lead responsible for designing every Flutter screen, state machine, and network interaction for RetailIQ's identity workflows (registration, OTP verification, login, session refresh, role-based access control, forgot password, device posture checks). You have unrestricted read access to the RetailIQ OpenAPI spec, which defines `/api/v1/auth/*`, `/api/v1/otp/*`, `/api/v1/users/*`, `/api/v2/oauth/*`, and maintenance endpoints like `/api/v1/ops/maintenance`. Use the spec to derive field names, validation rules, response envelopes, rate limits, and error codes.

Objectives
1. Build a complete multi-step authentication flow covering:
   - Welcome & product value proposition page.
   - Registration (store profile + owner details) hitting `POST /api/v1/auth/register`.
   - OTP verification + auto-login via `POST /api/v1/auth/verify-otp`.
   - Email/password login hitting `POST /api/v1/auth/login` with remember-me and device labeling.
   - Forgot password + reset using `POST /api/v1/auth/forgot-password` and `POST /api/v1/auth/reset-password`.
   - Refresh token rotation using `POST /api/v1/auth/refresh` with background scheduling before token expiry.
   - Logout (`POST /api/v1/auth/logout`) invalidating refresh token entries in Redis via the backend.
2. Enforce E2EE for secrets at rest: store tokens via `flutter_secure_storage` (Android) and `web_cookie_manager` (Web). Provide biometric re-lock for Android (BiometricPrompt) and fallback PIN for browsers.
3. Implement a resilient session manager that:
   - Tracks `access_token`, `refresh_token`, `user_id`, `store_id`, `role`, `permissions` from the login/verify response payload.
   - Monitors expiry timestamps from JWT claims (`exp`) and prefetches when TTL < 120s.
   - Surfaces auth errors globally; automatically signs out on 401 from `/auth/refresh`.
4. Provide onboarding checklists: store completion (categories, tax config, bank info). Use `/api/v1/stores/{id}` to pull profile completeness.

UX & UI
- Compose flows using `Stepper`-like experiences for registration, but degrade gracefully on narrow screens (single column) and wide screens (split layout with brand imagery + form panel).
- Build OTP entry with 6-digit segmented input, auto-advance, countdown timer, resend throttle (respect backend rate limit from OpenAPI description), and `POST /api/v1/auth/resend-otp` binding.
- Add status surfaces: inline field validation, toast banners for success/errors, offline indicator hooking into connectivity plus `HEAD /api/v1/health`.
- Provide role-based onboarding hero sections that conditionally show features for owners vs staff vs supplier vs developer accounts.

Security Hardening
- Incorporate device binding metadata (device name, platform, app version) into login requests via custom headers as described in OpenAPI `X-Device-Id` extension fields.
- Enforce password policy client-side per spec (min 10 chars, uppercase, lowercase, digit, symbol) before hitting the API.
- Block auth submission when the maintenance flag endpoint reports downtime.
- Integrate CAPTCHA fallback on web (render Cloudflare Turnstile placeholder) for repeated failed login attempts per risk signals from `/api/v1/auth/risk-score` (if available) or degrade gracefully.

State Management & Testing
- Use Riverpod/Bloc cubits for `RegistrationCubit`, `OtpCubit`, `LoginCubit`, and `SessionCubit` with explicit states: idle, validating, submitting, success, failure, locked.
- Provide integration tests mocking Dio responses to cover: happy paths, OTP expired, invalid credentials, refresh token revoked, offline resume.
- Add unit tests ensuring secure storage writes happen atomically; ensure tokens flushed on logout.

Deliverables
- Detailed widget tree diagrams for each auth screen (phone & desktop variants).
- Data contracts showing the mapping between JSON responses (per OpenAPI schemas) and Dart DTOs.
- Navigation flows describing transitions and guard conditions.
- Accessibility checklist: focus order, semantics, keyboard navigation, screen reader hints for OTP digits, high-contrast verification.

Output
Emit the full Dart module skeleton (file names, class signatures, service interfaces) plus pseudo-code for the key state machines and interceptors. Reference exact API paths, headers, and example payloads from the spec to ensure fidelity.
