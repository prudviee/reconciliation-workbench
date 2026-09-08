# 007 Local-only Storage Simplification — Tasks

- **Status:** Complete
- **Specification:** [spec.md](./spec.md)
- **Plan:** [plan.md](./plan.md)

- [x] **STO-T01 — Remove unused external storage support** (`STO-001`–`STO-005`)
  - Remove the adapter, configuration, SDK dependencies, and adapter-specific tests.
  - Keep private local storage, authorized downloads, and expiry deletion intact.
  - Update current design and deployment documentation.
  - Verify focused behavior, dependency closure, full regression, Docker health, and the browser journey.
  - Record evidence in `evidence/STO-T01.md`.
