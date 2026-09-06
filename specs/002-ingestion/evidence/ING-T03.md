# ING-T03 Evidence — Private Bounded Artifact Intake

- **Task:** ING-T03
- **Result:** Passed
- **Date:** 6 September 2026
- **Environment:** Python 3.12.14, Django 5.2.17, PostgreSQL 17.6, Windows temporary filesystem

## Implemented boundary

CSV input is streamed into a private quarantine file through bounded byte chunks while SHA-256 is calculated over the exact bytes. The scanner decodes strict UTF-8 with optional BOM, accepts only an explicit comma, semicolon, or tab delimiter, and enforces 25 MiB, 10,000 data-row, 100-column, and 4,096 decoded-character field defaults.

Validated bytes move atomically within the private root to a generated workspace path. Neither the submitted filename nor content type influences that path. Display filenames are reduced to a printable basename and content types are allowlisted.

Before staging, the workspace must be active. Publication reserves retained-byte quota under the existing workspace row lock. Database failure rolls back the quota transaction and removes the published file; validation, quota, and revoked-workspace failures retain neither a file nor an artifact record.

## Verification

| Check | Command scope | Result |
|---|---|---:|
| Artifact intake | `tests/test_artifact_intake.py` | 25 passed |
| Full regression suite | all tests | 161 passed |
| Django system check | registered configuration | 0 issues |
| Migration drift | models against committed migrations | no changes detected |

The focused suite covers chunked hashing, exact-byte retention, BOM input, all three delimiters, scan metadata, each limit at and one beyond its boundary, invalid encoding, malformed/empty CSV, unsupported delimiters, path traversal, untrusted metadata, quota refusal, injected database failure compensation, and revoked workspace refusal.

## Storage deployment contract

Local configuration defaults to a Git-ignored private directory. Compose mounts one named artifact volume at `/var/lib/reconciliation/artifacts` in both web and worker services, outside static serving. Clean-stack verification of that volume remains part of ING-T11.

## Remaining acceptance scope

This task deliberately stops at safe artifact intake and structural CSV scanning. Mapping, tagged raw-row persistence, row-level preview messages, authorized downloads, retention cleanup, and activation are covered by later tasks.
