# FND-T04 Verification Evidence

- **Task:** Resolve workspaces through secure server-side sessions
- **Requirements:** `FND-001`, `FND-002`, `FND-005`, `FND-008`
- **Acceptance scenarios:** `FND-A01`, `FND-A02`, `FND-A03`, `FND-A08`
- **Date:** 5 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `FND-T04`

## Implemented scope

- Database-backed Django sessions used as the anonymous browser credential.
- First binding rotates an existing unbound session key and retains its benign session data.
- The workspace stores only a keyed SHA-256 digest of the session key.
- Middleware resolves protected views to an immutable `WorkspaceAccess`; health checks remain workspace-free.
- Book read and rename routes derive ownership from `WorkspaceAccess` and return the same unavailable response for foreign and random UUIDs.
- Django CSRF enforcement remains active on mutations.
- Production settings require explicit secret, host, trusted HTTPS origin, and PostgreSQL URL values and enable HTTPS, HSTS, and secure cookies.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Complete current suite | Pass | 49 tests passed against an isolated PostgreSQL test database. |
| First-session binding | Pass | An existing unbound key rotated before binding; session data survived; exactly one workspace was created. |
| Secret handling | Pass | The stored 64-character keyed digest differed from the raw session key. |
| Refresh persistence | Pass | Repeated home requests reused the same workspace and did not create a duplicate. |
| Request cost | Pass | A same-session protected request issued exactly one indexed workspace-table lookup. |
| Session independence | Pass | Two clients received different sessions and workspace UUIDs. |
| Operational endpoint isolation | Pass | Readiness succeeded without creating a visitor workspace. |
| HTTP read isolation | Pass | The owner received the book; foreign and random UUID requests had equal status, body, and content type. |
| HTTP mutation isolation | Pass | Foreign and random rename attempts had equal unavailable responses and did not change the owner's data. |
| CSRF | Pass | A rename without CSRF proof returned 403; the same owner mutation with a valid token succeeded. |
| Cookie attributes | Pass | The emitted production-like session cookie was Secure, HttpOnly, and SameSite=Lax. |
| Production fail-closed validation | Pass | Missing settings, debug mode, short secrets, wildcard hosts, and non-HTTPS trusted origins prevented startup. |
| Production transport/database parsing | Pass | A complete configuration enabled SSL redirect, one-year HSTS, secure CSRF/session cookies, and parsed the PostgreSQL target. |
| Migration and Django checks | Pass | No migration drift; Django reported no system-check issues. |

## Remaining evidence

`FND-A01` still requires the polished workspace disclosure page in `FND-T06`. Expired and deleted session behavior is completed in `FND-T07`. Structured-log privacy remains in `FND-T08`. Every resource type added by later specifications must join the same isolation contract.
