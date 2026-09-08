# UX-T08B reviewer-facing comparison values

## Acceptance matrix

| Requirement | Evidence | Result |
|---|---|---|
| Persisted typed values remain unchanged for durable evidence and exports | Query projection retains all four original typed fields | Pass |
| Comparison values render without Python dictionary syntax | Browser workflow assertions for decimal, datetime, and timedelta keys | Pass |
| UTC timestamps state their timezone | Browser workflow assertion for the formatted timestamp | Pass |
| Time differences and tolerances use concise human units | Browser workflow assertion for the one-minute tolerance | Pass |
| Missing comparison values have an explicit label | Formatter contract maps `None` to an em dash | Pass |

## Verification record

- Focused workflow test: `1 passed, 16 deselected`.
- Related browser-workflow regression: `17 passed`.
- Full PostgreSQL regression: `533 passed`.
- Django system check: no issues; migration drift check: no changes detected.
- Live browser verification on the `TX-1002 ↔ TX-1002` discrepancy:
  - decimals rendered as `7000`, `7000.2`, and difference `0.2` with allowed `0.05`;
  - timestamps rendered as `2026-09-01 10:30:00 UTC`;
  - the zero time difference and tolerance rendered as `0 s (allowed 1 min)`;
  - missing numeric differences rendered as an em dash;
  - statuses and retained comparison explanations remained visible.
- Diff hygiene: passed; only repository line-ending conversion notices were emitted.
