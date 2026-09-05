# FND-T06 Verification Evidence

- **Task:** Render workspace disclosures and independent demo books
- **Requirements:** `FND-003`, `FND-006`, `FND-012`
- **Acceptance scenarios:** `FND-A01`, `FND-A07`, `FND-A12`
- **Date:** 5 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence; see Git history for `FND-T06`

## Implemented scope

- Server-rendered workspace page with restrained financial-operations visual design.
- Exact UTC expiry, fixed-expiry behavior, private-workspace scope, browser-data loss/no-recovery, export path, and deletion disclosures.
- Usage summary for book, retained-storage, and active-job quotas.
- CSRF-protected demo-book creation with post/redirect/get behavior.
- Independent user/demo book cards and an empty state that works without JavaScript.
- Clear quota refusal that leaves existing books visible.
- Responsive single-column mobile layout, visible keyboard focus, skip navigation, text status labels, reduced-motion handling, and tabular numeric styling.

## Checks and results

| Check | Result | Evidence summary |
|---|---|---|
| Focused workspace-page suite | Pass | 7 server-side page, workflow, privacy, CSRF, and stylesheet tests passed. |
| Full regression suite | Pass | 67 tests passed after removing a duplicate workspace query. |
| Required disclosures | Pass | The rendered page included the exact persisted expiry plus privacy, fixed expiry, no recovery, export, and deletion wording. |
| No-JavaScript flow | Pass | The page contained ordinary POST forms with CSRF tokens and no script dependency. |
| Multiple-book behavior | Pass | Two demo books received distinct IDs while an existing user book remained unchanged. |
| Session isolation | Pass | Two clients retained independent demo lists and persisted counts of 2 and 1. |
| Quota failure | Pass | At a one-book limit, the second request returned an announced clear refusal and retained the first book. |
| Query budget regression | Pass | Rendering reuses the middleware-authorized workspace record; a refresh remains at one workspace lookup. |
| Desktop browser review | Pass | The default viewport showed a coherent hero, privacy card, quota strip, primary action, and readable hierarchy with no clipped content in the reviewed viewport. |
| Demo browser interaction | Pass | Activating **Use demo dataset** navigated through POST/redirect/GET, announced success, changed the visible count from 0/10 to 1/10, and rendered the new card. |
| Narrow-screen browser review | Pass | At 390 × 844 pixels, actions and metrics stacked, cards remained readable, policy content stayed in one column, and measured horizontal overflow was absent. |
| Keyboard skip | Pass | The first Tab focused **Skip to workspace** and activation moved focus to `main-content`. |
| Semantic review | Pass | Browser accessibility output exposed named landmarks, headings, buttons, status copy, definition lists, and text-backed states. |
| Migration and Django checks | Pass | No migration drift; Django reported no system-check issues. |

## Defect found before commit

The initial page implementation fetched the workspace once in session middleware and again while rendering usage, exceeding the one-lookup target. Middleware now carries the already-authorized record in request context. Browser review also found that skip navigation scrolled without moving focus; the main landmark is now programmatically focusable.

## Remaining evidence

The deletion disclosure and disabled control are present in this task. `FND-T07` makes deletion functional, revokes access synchronously, and verifies expiry and late-worker behavior before the public release gate.
