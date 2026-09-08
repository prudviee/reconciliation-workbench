# Atlas submission demo

Use [atlas-ledger.csv](./atlas-ledger.csv) for the left **Internal ledger** source and [atlas-counterparty.csv](./atlas-counterparty.csv) for the right **Counterparty** source.

## Three outcomes in one run

- `TX-1001` demonstrates an exact authoritative-reference pair.
- `TX-1002` demonstrates a paired transaction with a visible gross-amount discrepancy: `7000` versus `7000.20` against the configured `0.05` tolerance.
- `TX-1003` and `CP-9003` remain unpaired while retaining a low-scoring candidate. This exposes the reasoned manual-link flow.

## Five-minute walkthrough

1. Create a demo book and open **Prepare sources**.
2. Upload `atlas-ledger.csv` on the left, inspect the raw/canonical preview and field lineage, then activate it.
3. Upload `atlas-counterparty.csv` on the right using the Counterparty adapter, inspect the preview, then activate it.
4. Open the workbench and start reconciliation.
5. Open the `TX-1002` pair to show the field-level discrepancy and tolerance explanation.
6. Open the `TX-1003` unpaired case, choose the retained candidate, enter `Confirmed against settlement statement`, and save the manual link.
7. Return to the workbench, run again, and show the new manual pair plus the preserved historical run.

The fixtures contain synthetic data and are safe to publish with the repository.
