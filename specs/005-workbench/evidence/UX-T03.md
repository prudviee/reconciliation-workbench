# UX-T03 verification

## Scope

Current cases now open a workspace-scoped evidence page. The page presents the retained left/right raw rows and canonical values, source row and observation identities, field lineage, comparison values and tolerance explanations, candidate evidence where applicable, run and policy versions, occurrence history, current review health, and bidirectional case lineage.

## Verification

- Focused browser journey: `5 passed, 7 deselected`.
- Full regression suite: `464 passed`.
- Django system checks: passed.
- Migration drift check: passed (`No changes detected`).
- `git diff --check`: passed.

The acceptance test starts a run through the browser, follows a case link from the current review table, and verifies raw/canonical evidence, comparison explanations, occurrence history, policy metadata, source identity, and the no-JavaScript boundary.
