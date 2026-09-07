# ING-T10 Evidence — Source Preparation Interface

- **Task:** ING-T10
- **Result:** Passed
- **Date:** 7 September 2026
- **Environment:** Python 3.12.14, Django 5.2.17, PostgreSQL 17.6, Codex in-app Chromium browser

## Implemented workflow

Each reconciliation book now opens a two-sided source-preparation workspace. A reviewer can upload either predefined Atlas format, define and version a configurable third-source contract, select the recorded delimiter, and inspect an immutable preview before publication.

The preview presents file and semantic identities, expected base, operation counts, original tagged cells, canonical values, field lineage, and row-level validation. Fifty-row server-side pagination keeps large previews bounded. Ready previews expose a CSRF-protected confirmation action; rejected or stale previews show their reason and a recovery path. Import detail pages retain the original download and dataset revision history after activation.

The workflow is server rendered and has no JavaScript dependency. Tables scroll within their container on narrow screens, controls retain visible focus behavior, reduced-motion preferences are honored, and status/error states use semantic landmarks.

## Browser review

| View | Width | Result |
|---|---:|---|
| Two-sided source preparation | default app viewport | both source cards, actions, privacy explanation, and navigation visible |
| One-row raw/canonical preview | default app viewport | evidence table, hashes, activation, download, and history visible; no page overflow |
| One-row raw/canonical preview | 375 px content viewport | summary stacks, table scroll remains contained, activation action becomes full width |
| Activation result | default app viewport | success state and immutable revision history rendered |

Browser inspection found meaningful content, no framework error overlay, no horizontal page overflow, and no console errors. The complete upload → preview → activate flow succeeded using the assignment ledger format.

## Automated verification

| Check | Result |
|---|---:|
| Complete workflow scenarios | 7 passed |
| Predefined upload, raw/canonical/provenance preview, activation and history | passed |
| Configurable semicolon-delimited third format | passed |
| Accessible row errors and activation blocking | passed |
| 61-row pagination under a 12-query ceiling | passed |
| Stale activation recovery | passed |
| Foreign/random import parity | passed |
| Full regression suite | 228 passed |
| Django system check | 0 issues |
| Migration drift | no changes detected |

## Remaining acceptance scope

ING-T11 measures the 10,000-row boundary, records parse/activation resource use, rebuilds a clean Compose stack, closes final traceability, and updates the public README to the verified ingestion scope.
