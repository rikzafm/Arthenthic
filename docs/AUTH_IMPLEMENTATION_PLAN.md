# Arthentic Mobile: Auth, App Lock & Role Access, Implementation Plan

## 0. Decisions locked in (from the Q&A)

| Topic | Decision |
|---|---|
| Auth backend | Own FastAPI auth (JWT access + rotating refresh tokens) |
| Platform | iOS only (Face ID, Keychain) |
| App lock | Face ID, fallback to **device passcode** (no server round-trip) |
| Roles | Artist, Gallery (Verifier), Collector, Conservator, Admin. One user can hold several roles. |
| System accounts | Protocol Node, Paymaster: **not logins**; out of scope for app auth |
| Guest | Anonymous: scan NFC, view certificate/provenance, run L1 & L2 verify. No account, no app lock. |
| Gallery / Admin | Sign in with email/Google; mobile is **read-only**, multisig signing stays on web |
| Wallet | **Off-chain RBAC now**; passkey smart wallet and on-chain role sync are a later phase |
| Accreditation | Artist/Gallery/Conservator apply in-app, Admin approves manually. No KYC vendor in v1. |

Assumptions to confirm (flagged where they matter):
- A1. "30 days" is an **absolute cap from the last full login** (password/Google), not sliding forever.
- A2. Lock triggers on every cold start and on resume after a background grace period (default 30 s, setting-controlled, min 0 s).
- A3. Sign in with Apple will be added alongside Google (App Store Guideline 4.8). See Risks.

---

## 1. System Architecture & Data Model

### 1.1 Architecture

```
Flutter app (iOS)                          FastAPI server
┌──────────────────────────┐               ┌─────────────────────────────┐
│ AuthController (Riverpod)│  HTTPS/JSON   │ /auth/*  signup, login,     │
│  ├ SessionStore (Keychain)│◄────────────►│          google, refresh,   │
│  ├ AppLockService         │               │          logout, me         │
│  │   (local_auth)         │               │ /roles/* applications,      │
│  ├ GoogleSignIn           │               │          admin review       │
│  └ Role router/guards     │               │ require_role() dependency   │
│ Guest mode (no session)   │               │ DB (Postgres; SQLite in dev)│
└──────────────────────────┘               └─────────────────────────────┘
```

Two independent layers, kept deliberately separate:
1. **Session** (server-issued): proves *who you are*. Lives 30 days. Tokens in Keychain.
2. **App lock** (device-local): proves *the person holding the phone is the owner*. Gates UI access to the session each open. Never sent to the server.

Token model:
- Access JWT: 15 min, contains `sub`, `roles[]`, `sid` (session id). Held in memory only.
- Refresh token: opaque 256-bit random, 30-day absolute expiry, **rotated on every use**, stored hashed (SHA-256) server-side, stored in Keychain on device (`kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly`, so it is deleted if the passcode is removed and never syncs to iCloud).
- Reuse of an already-rotated refresh token revokes the whole token family (theft detection).
- Passwords: Argon2id. Google: ID token verified server-side (signature, `aud`, `iss`, `exp`, `email_verified`).

### 1.2 Entities

```
users
  id (uuid pk), email (unique, citext), email_verified_at, display_name,
  password_hash (nullable: Google-only users), status (active|suspended|deleted),
  created_at, last_login_at

auth_identities                       -- one row per external login method
  id, user_id fk, provider (google|apple), provider_subject,
  email_at_link, created_at
  UNIQUE (provider, provider_subject)

devices
  id, user_id fk, install_id (client-generated uuid), name, platform,
  created_at, last_seen_at, revoked_at

sessions                              -- one per device login
  id, user_id fk, device_id fk, absolute_expires_at (login + 30d),
  revoked_at, revoke_reason, created_at

refresh_tokens                        -- rotation chain
  id, session_id fk, token_hash (unique), family_id,
  replaced_by fk null, used_at null, expires_at, created_at

role_assignments                      -- User 1:N RoleAssignment
  id, user_id fk, role (artist|gallery|conservator|admin),
  status (active|revoked), granted_by fk users, granted_at, revoked_at,
  onchain_tx_hash null                -- filled in the wallet phase
  UNIQUE (user_id, role) WHERE status='active'
  -- Collector = a users row with no assignment (derived, per your model)

role_applications
  id, user_id fk, requested_role, status (pending|approved|rejected|more_info),
  payload jsonb, reviewed_by fk null, reviewed_at, review_note, created_at

artists / galleries / conservators    -- accredited profiles (1:1 with user+role)
  id, user_id fk, display_name, bio/org_name, website, verification_notes, ...

application_documents
  id, application_id fk, storage_key, mime, sha256, created_at

audit_log                             -- append-only
  id, actor_user_id, action, target_type, target_id, ip, device_id, meta jsonb, at

wallet_links (LATER PHASE)
  id, user_id fk, kind (passkey_smart_wallet|metamask|safe), address, chain_id, created_at
```

Relationships: `users 1─N auth_identities, devices, sessions, role_assignments, role_applications`; `sessions 1─N refresh_tokens`; `role_applications 1─N application_documents`; `role_assignments` created only by an Admin approving an application (or bootstrap seed for the first Admin).

Existing `captures`, `genesis`, `provenance` tables get `owner_user_id` / `created_by` foreign keys in Milestone 5.

### 1.3 Permission matrix (v1, mobile)

| Capability | Guest | Collector | Artist | Gallery | Conservator | Admin |
|---|---|---|---|---|---|---|
| Scan NFC, view cert/provenance, L1/L2 verify | yes | yes | yes | yes | yes | yes |
| Save verification history, own works | no | yes | yes | yes | yes | yes |
| Apply for an accredited role | no | yes | n/a | n/a | n/a | n/a |
| Register artwork (genesis capture) | no | no | yes | no | no | no |
| Bulk / batch verify, verification reports | no | no | no | yes (read-only; sign on web) | no | no |
| Condition reports | no | no | no | no | yes | no |
| Review applications, grant/revoke roles, view audit log | no | no | no | no | no | yes |

Enforced **server-side** by a `require_role(...)` dependency. The app hides UI as a convenience only.

---

## 2. Development Milestones

**M0: Foundations (1 to 2 days)**
- Migrate auth routes to a real DB layer (SQLAlchemy + Alembic), config via env, add `users`, `devices`, `sessions`, `refresh_tokens`, `audit_log`.
- Dev seed: one user per role. CI: pytest runs on every push.
- Exit: migrations apply clean; existing tests still green.

**M1: Email/password sign up, login, persistent session (MVP core)**
- Server: `POST /auth/signup`, `/auth/login`, `/auth/refresh` (rotation + reuse detection), `/auth/logout`, `GET /auth/me`. Rate limiting, Argon2id, audit events.
- App: Login + Sign Up screens, `SessionStore` (Keychain), auto-refresh interceptor, splash that restores session.
- Exit: log in, kill app, relaunch → still signed in; session dies after 30 days (test with clock override); logout revokes server-side.

**M2: App lock (Face ID / device passcode)**
- `AppLockService` using `local_auth` (`biometricOrDevicePasscode`); `NSFaceIDUsageDescription` in Info.plist.
- Lock overlay on cold start and on resume after grace; hide content in app-switcher snapshot; lockout after repeated fails handled by iOS.
- If device has no passcode: block "stay signed in", require login each launch.
- Exit: logged-in user cannot reach any authenticated screen without unlock; guest unaffected.

**M3: Login with Google (+ Sign in with Apple)**
- Server: `POST /auth/google` (verify ID token, link-or-create by `(google, sub)`; auto-link to an existing email account **only** if `email_verified` and the existing account's email is verified).
- App: `google_sign_in` iOS client ID + reversed URL scheme; handle cancel / network errors.
- Sign in with Apple endpoint and button (required for App Store).
- Exit: new Google user created; returning Google user signs in; password user can link Google from settings.

**M4: Roles & role-based home**
- `role_assignments`, `/me` returns `roles[]`; `require_role()` guard; JWT carries roles (re-checked against DB on sensitive actions).
- App: role router → per-role home; role switcher for multi-role users; guest entry from the Login screen.
- Seed Admin bootstrap command (CLI, not an API).
- Exit: matrix in 1.3 verified by tests per role, including direct-API attempts that must return 403.

**M5: Accreditation flow + role-specific features**
- Collector: "Apply for Artist / Gallery / Conservator" (form + documents).
- Admin (mobile, read-only list + approve/reject in v1; or web, decide before starting): review queue → grant `RoleAssignment`, notify user.
- Wire genesis to Artist; owner FKs on captures/verifications; Gallery read-only batch results; Conservator condition-report stub.
- Exit: end-to-end apply → approve → role appears after token refresh.

**M6: Hardening & account management**
- Session/device list with remote revoke, change password, forgot/reset password (emailed one-time link), email verification, delete account (App Store requirement), security audit view.
- Pen-test checklist, dependency scan, privacy policy, crash/telemetry without PII.
- Exit: threat-model items in section 4 closed or accepted.

**M7: Release**
- TestFlight beta, staged rollout, monitoring (auth failure rates, refresh failures, lock-bypass reports), runbook for token-signing-key rotation.

**Later phase (not in this plan's scope):** passkey smart wallet (ERC-4337), MetaMask fallback, on-chain role sync (`onchain_tx_hash`), Safe/multisig flows, Paymaster, KYC vendor, splitting Admin into Admin + Anchorer.

---

## 3. Core Workflows / Screens

**Launch routing**
```
Cold start → Splash
  ├ no session in Keychain      → Welcome (Login / Sign Up / Continue as Guest)
  ├ session expired/revoked     → Login (message: "Session expired")
  └ valid session               → Lock screen → [Face ID ok / passcode ok] → Role home
```

| Screen | States / notes |
|---|---|
| Welcome | Login, Sign Up, "Continue as guest" |
| Sign Up | email, password (strength meter), name; errors: email taken, weak password, offline. Then "verify email" notice. |
| Login | email + password, "Continue with Google", "Sign in with Apple", forgot password. States: loading, invalid creds (generic message), rate-limited, suspended. |
| Lock screen | Face ID prompt auto-shows; buttons: "Use passcode", "Sign out". States: failed, cancelled, biometrics unavailable, no passcode set. |
| Guest Verify | Existing Verify / Scan / Result. Banner: "Sign in to save results". |
| Collector home | Recent verifications, owned works, "Apply for accreditation" card. |
| Artist home | My works, "Register new artwork" (genesis), status of applications. |
| Gallery home | Verification queue/reports (read-only); "Sign on web" explainer for multisig actions. |
| Conservator home | Condition reports list. |
| Admin home | Pending applications, role grants, audit log (read-only on mobile). |
| Role switcher | Bottom sheet for multi-role users; remembers last role per device. |
| Apply for role | Form + document upload; states: draft, pending, more info requested, approved, rejected. |
| Settings | Lock timing, linked accounts (Google/Apple), devices & sessions, change password, sign out, delete account. |

---

## 4. Edge Cases & Risks

**Auth / session**
- Refresh token stolen or replayed → reuse detection revokes family; user gets "signed out for security".
- Two concurrent requests both hit 401 and refresh at once → single-flight refresh in the client, or the second one trips reuse detection and logs the user out. Mitigate with a mutex and a short server grace window for the immediately previous token.
- Clock skew on device → rely on server `exp`; never compute 30 days on the client.
- Network loss during refresh → don't log out on transport errors; only on explicit 401 from `/refresh`.
- Keychain survives app uninstall on iOS → on first launch after install, clear stale tokens (install-marker in UserDefaults).
- Device restored from backup to a new phone → `ThisDeviceOnly` blocks transfer; user logs in again (expected).

**App lock**
- Face ID not enrolled, locked out, or user removes passcode → define behaviour: fall to passcode; if no passcode exists, disable persistence and require full login.
- Face ID spoofing or biometric set changed → acceptable fallback is device passcode (your choice); note anyone who knows the device passcode can enter. If this is unacceptable for Artists/Admins, add optional account-password re-entry for those roles later.
- Lock only protects UI; a jailbroken device can read Keychain. Add jailbreak detection as a warning, not a hard block.
- Screenshots in app switcher expose data → blur overlay on `inactive`.
- Deep links / NFC launches while locked → queue the intent, unlock first, then handle. Guests bypass the lock but the app-lock applies once signed in.

**Google / account linking**
- Account takeover via email match: only auto-link when both emails are verified; otherwise require password login then link.
- User changes Google email → match on `sub`, never on email.
- Google user has no password → "forgot password" becomes "set a password".
- **App Store rejection** risk if Google is offered without Sign in with Apple (Guideline 4.8) and if account deletion isn't in-app (5.1.1(v)). Both are in the plan.

**Roles**
- JWT carries stale roles after revoke → short 15-min TTL plus DB re-check on sensitive endpoints; Admin revoke also kills the user's sessions.
- Last Admin removes themselves → block; require at least one active Admin.
- Admin approving own application → forbid; log everything in `audit_log`.
- Role in UI but 403 on API → UI is not the control; test direct API calls.
- Off-chain roles drift from on-chain `ARTIST_ROLE` etc. later → keep `onchain_tx_hash` nullable and build a reconcile job in the wallet phase; treat on-chain as source of truth then.

**Data & privacy**
- Application documents (IDs) are sensitive → private bucket, signed short-lived URLs, encrypted at rest, retention policy, never in logs.
- Email enumeration → identical responses for signup/login/reset where feasible.
- Brute force / credential stuffing → per-IP and per-account rate limits, progressive delay, optional CAPTCHA later.
- Account deletion vs audit-log retention and provenance records → anonymise the user, keep the immutable provenance data.

**Performance / ops**
- Argon2id cost vs login latency → tune to ~100 to 250 ms on the server.
- Refresh storm after an outage → jitter client retries.
- Token signing-key rotation → support `kid` with two active keys.
- SQLite in dev vs Postgres in prod behave differently (citext, partial unique indexes) → run CI against Postgres.

---

## 5. Recommended First Prompt (Milestone 0 + 1)

> Read `README.md`, `server/` (especially `routes/` auth and `main.py`) and `app/lib/` to understand the current structure. Then implement **Milestone 0 and 1** from `docs/AUTH_IMPLEMENTATION_PLAN.md`.
>
> **Backend (FastAPI):** add SQLAlchemy + Alembic with tables `users`, `devices`, `sessions`, `refresh_tokens`, `audit_log`. Implement `POST /auth/signup`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`. Passwords use Argon2id. Access JWT lasts 15 minutes. Refresh tokens are opaque, hashed at rest, rotated on every use, capped at 30 days absolute, with reuse detection that revokes the token family. Add rate limiting on login/signup and write audit-log entries. Do not touch role logic yet.
>
> **Flutter app:** add Login and Sign Up screens in the existing theme, a `SessionStore` backed by `flutter_secure_storage` (iOS Keychain, `WhenPasscodeSetThisDeviceOnly`), an HTTP client that refreshes on 401 with single-flight locking, and a splash screen that restores the session. Keep the existing Verify/Scan/Result flow reachable as guest ("Continue as guest").
>
> **Tests:** pytest for rotation, reuse detection, expiry at 30 days (with an injectable clock), and rate limiting; a Flutter widget test for the launch routing. Do not add Face ID, Google, or roles yet. Run the tests, list what you changed, and stop for review before Milestone 2.
