# FND-T08 Verification Evidence

- **Task:** Add correlation and privacy-safe structured logs
- **Requirement:** `FND-009`
- **Acceptance scenario:** `FND-A09`
- **Date:** 6 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `FND-T08`

## Implemented scope

- A request-boundary correlation ID accepts only 1–64 characters from a conservative identifier alphabet; missing or invalid input is replaced with a generated value.
- The correlation ID is attached to the request, returned in `X-Correlation-ID`, and included in the completion event.
- Request completion uses a fixed schema: event, correlation ID, resolved route name, method, status, duration, irreversible workspace pseudonym, and typed failure category.
- The logger formatter serializes only reviewed scalar fields. It ignores the log message and drops every unrecognized field.
- Middleware does not read request paths, query strings, headers other than the correlation header, cookies, bodies, form values, session keys, or upload contents for logging.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused telemetry suite | Pass | 8 correlation, redaction, schema, formatter, and successful/failed request tests passed. |
| Full regression suite | Pass | 84 tests passed against isolated PostgreSQL 16.11. |
| Successful request | Pass | A caller-supplied valid correlation ID was echoed and logged with the resolved route and an irreversible workspace reference. |
| Failed request | Pass | A CSRF-rejected POST produced status 403, a correlation ID, and the `client_error` category. |
| Sensitive-value exclusion | Pass | Distinct values placed in a query, form body, untrusted cookie, and server session were absent from captured structured events and record messages. |
| Correlation validation | Pass | Empty, whitespace, line-break, and overlength identifiers were replaced with 32-character generated identifiers. |
| Fixed event schema | Pass | Unknown fields were discarded and non-scalar field values could not pass through unchanged. |
| Formatter boundary | Pass | JSON output contained only fixed-schema fields even when the conventional log message and extra data contained an untrusted value. |
| Migration consistency | Pass | `makemigrations --check --dry-run` reported no changes. |
| Django system check | Pass | `System check identified no issues (0 silenced).` |

## Environment note

Docker Desktop remains stopped because its engine startup encounters a stale internal socket permission failure. Verification used the existing isolated PostgreSQL 16.11 cluster on local port 55434. Docker volumes and runtime data were not modified.

## Scope boundary

This task establishes and verifies the safe transport for request events. Later lifecycle, import, reconciliation, and publication work must emit through the same allowlisted formatter and add only reviewed non-financial metadata.
