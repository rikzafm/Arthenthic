# Operational Runbook: Token-Signing-Key Rotation

This runbook provides step-by-step instructions for zero-downtime rotation of the JWT access-token signing secret keys in Arthentic Mobile Backend per Milestone 7 of [AUTH_IMPLEMENTATION_PLAN.md](file:///Users/rkz/Documents/Project_Folder/Arthenthic-Mobile/docs/AUTH_IMPLEMENTATION_PLAN.md).

---

## 1. Architecture & Background

Arthentic access tokens are signed using HMAC-SHA256 (`HS256`) and valid for **15 minutes**.
To prevent service interruption or mass session invalidation during key rotation, Arthentic supports multi-key verification using the standard JWT `kid` (Key Identifier) header.

```
Access Token JWT Header:
{
  "alg": "HS256",
  "kid": "v2",       <-- Key identifier
  "typ": "JWT"
}
```

The server maintains a registry of active keys (`JWT_KEYS`) where:
* `JWT_ACTIVE_KID`: The key ID used to sign all newly generated access tokens (`/auth/login`, `/auth/refresh`, `/auth/google`, `/auth/apple`).
* `JWT_KEYS`: A map of `{ kid: secret }` containing all currently valid keys accepted for token verification.

---

## 2. Standard Zero-Downtime Rotation Procedure

### Phase 1: Pre-Rotation Checklist (T - 15 minutes)
1. Generate a new high-entropy 256-bit secret key:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
2. Verify current monitoring health:
   ```bash
   curl -H "Authorization: Bearer <ADMIN_TOKEN>" https://api.arthentic.io/v1/admin/monitoring/stats
   ```
   Ensure `auth.login_failure_rate < 0.01` and `tokens.token_reuse_events == 0`.

### Phase 2: Register New Secondary Key (Dual-Key Verification Active)
1. Add the new key to the deployment environment variables without switching the active key yet:
   ```bash
   JWT_SECRET_KEY=<CURRENT_V1_SECRET>
   JWT_ACTIVE_KID=v1
   JWT_SECRET_KEY_SECONDARY=<NEW_V2_SECRET>
   JWT_SECONDARY_KID=v2
   ```
2. Deploy the configuration.
3. At this stage, tokens signed by `v1` continue to be issued and verified, and any token signed by `v2` will also be accepted.

### Phase 3: Switch Active Signing Key to V2
1. Update the active key identifier:
   ```bash
   JWT_ACTIVE_KID=v2
   ```
2. Restart/reload the backend instances.
3. All new access tokens generated from logins and refreshes will now carry `"kid": "v2"` and be signed with `<NEW_V2_SECRET>`.
4. Existing access tokens signed with `v1` remain completely valid for up to 15 minutes.

### Phase 4: 15-Minute Drain & Monitoring Window
1. Monitor metrics on `/metrics` or the Admin dashboard:
   ```bash
   curl https://api.arthentic.io/metrics | grep auth_refresh
   ```
2. Wait for **16 minutes** (15-minute access token TTL + 1-minute clock skew leeway). All legacy `v1` tokens will have expired naturally and refreshed into `v2` tokens.

### Phase 5: Decommission Old V1 Key
1. Remove `v1` from the environment configuration:
   ```bash
   JWT_SECRET_KEY=<NEW_V2_SECRET>
   JWT_ACTIVE_KID=v2
   unset JWT_SECRET_KEY_SECONDARY
   ```
2. Redeploy. Key rotation is complete with zero user disruptions or session drops.

---

## 3. Emergency Key Compromise Procedure (Immediate Invalidation)

If a signing key is suspected of being compromised or leaked:

1. **Immediate Revocation**:
   Change `JWT_SECRET_KEY` immediately and wipe `v1` from `JWT_KEYS`.
2. **Revoke Active Refresh Sessions**:
   Run the administrative session revoke CLI or query:
   ```sql
   UPDATE sessions SET revoked_at = CURRENT_TIMESTAMP, revoke_reason = 'EMERGENCY_KEY_ROTATION' WHERE revoked_at IS NULL;
   ```
3. **Notify Users**:
   All active sessions will show "Session expired. Please sign in again" gracefully on next app open per [login_screen.dart](file:///Users/rkz/Documents/Project_Folder/Arthenthic-Mobile/app/lib/features/auth/login_screen.dart#L151).
4. **Post-Mortem**:
   Review `/v1/admin/audit-log` for any unauthorized access during the compromise window.

