# UX-T08D saved-decision review and reasoned revocation

## Acceptance matrix

| Requirement | Evidence | Result |
|---|---|---|
| A case exposes active saved authorities for its retained records | Case-detail workflow assertion | Pass |
| The management page previews every affected identity, current action, reason, actor, and revision | Decision-detail workflow assertions | Pass |
| Revocation requires a non-empty new reason | Blank-reason response and unchanged-revision assertions | Pass |
| Revocation appends a revision and preserves the original evidence | Decision history and persistence assertions | Pass |
| Revocation releases active claims and marks reconciliation pending | Claim and workbench assertions | Pass |
| Inactive or superseded authority cannot be revoked again | Inactive state and hidden-action assertion plus service concurrency contract | Pass |
| Foreign and absent decision identities are indistinguishable | Cross-workspace response equality assertion | Pass |

## Verification record

- Focused browser workflow test: `1 passed, 16 deselected`.
- Related decision and browser regression: `41 passed`.
- Full PostgreSQL regression: `533 passed`.
- Django system check: no issues; migration drift check: no changes detected.
- Live browser verification on the saved `TX-1003` unmatched authority:
  - the current case showed the active decision, record identity, original reason, and management link;
  - the decision page showed revision `1`, active authority, full record UUID, actor, and append-only history;
  - submitting reason `The settlement owner confirmed this exception should be reopened.` created revision `2` as `REVOKE`;
  - the page then showed inactive authority, both historical and current revisions, preserved original reason, and the new reason;
  - the revoke form disappeared and the workbench displayed `Changes are waiting for a rerun` while the prior result stayed visible.
  - the related case continued to show revision `2` as inactive and linked back to the complete decision history after the claim was released.
- Diff hygiene: passed; only repository line-ending conversion notices were emitted.
