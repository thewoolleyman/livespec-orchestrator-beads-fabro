"""livespec_orchestrator_beads_fabro — beads-backed implementation plugin for livespec.

The substrate is a per-repo beads tenant database on the shared
`dolt-server` (bd v1.0.5, server mode), reached through the `BeadsClient`
seam. Public package layout:

- `livespec_orchestrator_beads_fabro.types` — work-item dataclasses, the Spec
  Reader snapshot / diff dataclasses, and the `StoreConfig` beads
  connection descriptor.
- `livespec_orchestrator_beads_fabro._beads_client` — the `BeadsClient` backend seam
  (`ShellBeadsClient` over the pinned `bd` binary + a pure in-memory
  `FakeBeadsClient`), selected by `make_beads_client(*, config)`.
- `livespec_orchestrator_beads_fabro.store` — the store primitives (read /
  append / materialize for work-items) over the beads tenant.
- `livespec_orchestrator_beads_fabro.regroom` — backlog groom-out helpers used by
  the `groom` front-end to validate decomposition targets and explicitly
  dispose the original item after replacement slices are filed.
- `livespec_orchestrator_beads_fabro.intake_dor` — the intake Definition-of-Ready
  checklist, the shared capture-time triage primitive (evaluate / apply)
  every capture front-end calls to route a filed item into the seven-state
  lifecycle.
- `livespec_orchestrator_beads_fabro.spec_reader` — Spec Reader adapter implementing
  the four required capabilities defined in
  livespec/SPECIFICATION/contracts.md.
- `livespec_orchestrator_beads_fabro.errors` — exception types for the expected-error
  surface, including the beads backend errors (`BeadsConnectionError`,
  `BeadsCommandError`, `BeadsTenantMissingError`, `BeadsMappingError`).

The store and spec_reader modules are consumed by every heavyweight skill;
the types module is consumed by every skill plus the thin-transport CLIs.
"""
