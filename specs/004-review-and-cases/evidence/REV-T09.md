# REV-T09 Verification Evidence

- **Task:** Preserve complete merge and split lineage
- **Requirements:** `REV-010`, `REV-013`, `REV-014`, `REV-016`
- **Acceptance scenarios:** `REV-A07`, `REV-A08`, `REV-A12`
- **Date:** 7 September 2026
- **Result:** Pass
- **Task commit:** The commit containing this evidence

## Deterministic transition rule

Before replacing a scope's current projections, publication captures every prior current case. The pure transition planner compares those cases with every newly materialized occurrence. It appends `predecessor → successor` exactly when the stable case keys differ and their logical member sets overlap.

This one deterministic rule covers the required many-to-many behavior:

- two unpaired cases that become one pair both link to the pair;
- one pair that splits into two unpaired cases links to both successors;
- changed pair partners retain the shared endpoint's history;
- ambiguity cases whose complete membership changes link when any stable member continues;
- unrelated cases receive no edge;
- an unchanged stable case receives a new occurrence without a self-edge.

Input order does not affect the plan. Nodes and edges are canonicalized by case kind/digest, duplicate edges are rejected, and every node requires a nonempty unique member set.

## Durable lineage

`case_lineage` stores workspace, scope, predecessor, successor, the fixed `PREDECESSOR_OF` transition kind, caused-by run, and creation time. Rows are append-only, self-edges are prohibited, and each predecessor/successor/run edge is unique.

The integration fixture began with one pair, changed the right reference so the result split into two unpaired cases, then restored the shared reference so those cases merged back into the original stable pair. The split run stored both successors; the merge run stored both predecessors. Historical pair and unpaired occurrences remained navigable throughout.

Case identity constraints were tightened with lineage: pair and unpaired cases must have ambiguity metadata absent, ambiguity cases require both complete member lists, and pair endpoints must differ.

## Verification results

| Check | Result |
|---|---|
| Focused planner, merge/split, case, and review suite | 50 passed in 13.07 seconds |
| Full repository regression | 444 passed in 31.40 seconds |
| Django system check | Passed, 0 issues |
| Migration drift check | Passed, no changes detected |
| Diff whitespace check | Passed |

## Scope boundary

Lineage is created only during a fresh scope publication and never rewrites earlier cases or occurrences. REV-T10 will expose bounded workspace-scoped list, history, current-review, and lineage query services over this evidence.

