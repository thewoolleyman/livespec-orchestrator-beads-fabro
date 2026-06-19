"""livespec_impl_beads — beads-backed implementation plugin for livespec.

The substrate is a per-repo beads tenant database on the shared
`dolt-server` (bd v1.0.5, server mode), reached through the `BeadsClient`
seam. Public package layout:

- `livespec_impl_beads.types` — work-item and memo dataclasses, the Spec
  Reader snapshot / diff dataclasses, and the `StoreConfig` beads
  connection descriptor.
- `livespec_impl_beads._beads_client` — the `BeadsClient` backend seam
  (`ShellBeadsClient` over the pinned `bd` binary + a pure in-memory
  `FakeBeadsClient`), selected by `make_beads_client(*, config)`.
- `livespec_impl_beads.store` — the six store primitives (read /
  append / materialize for work-items and memos) over the beads tenant.
- `livespec_impl_beads.regroom` — the `needs-regroom` state machine, the
  shared grooming-lifecycle primitive (enter / exit / query) the capture
  front-ends, Dispatcher, and `groom` front-end consume.
- `livespec_impl_beads.intake_dor` — the intake Definition-of-Ready
  checklist, the shared capture-time triage primitive (evaluate / apply)
  every capture front-end calls to tag a filed item `ready` /
  `needs-regroom` / `not-yet-actionable`.
- `livespec_impl_beads.spec_reader` — Spec Reader adapter implementing
  the four required capabilities defined in
  livespec/SPECIFICATION/contracts.md
  §"Spec Reader required-capability surface".
- `livespec_impl_beads.errors` — exception types for the expected-error
  surface, including the beads backend errors (`BeadsConnectionError`,
  `BeadsCommandError`, `BeadsTenantMissingError`, `BeadsMappingError`).

The store and spec_reader modules are consumed by every heavyweight skill;
the types module is consumed by every skill plus the thin-transport CLIs.
"""
