# W9D: Final PR Credential Sentinel

This note is the artifact for `livespec-impl-beads-w9d`.

## Purpose

`livespec-impl-beads-w9d` existed solely as a proof target for the final
leg of the W7 Tier-2 dispatch proof, following `livespec-impl-beads-5qv`
(which added GH_TOKEN projection into the Fabro sandbox env table).

Its scope is intentionally doc-only: no production code, workflow
configuration, secrets, or runtime behavior changed.

## What It Proved

A fully containerized Fabro dispatch round-trip — from the
`livespec-orchestrator:dev` image through sandbox clone, implementation,
janitor, and branch push — can also complete the PR creation and merge steps
when `GH_TOKEN` is projected from `LIVESPEC_FAMILY_GITHUB_TOKEN` by the
proof wrapper and then materialized by the Dispatcher into the sandbox env
table.

This is the boundary condition that `livespec-impl-beads-ctq` could not
reach (no credential at the PR node), and that `livespec-impl-beads-5qv`
wired up. `w9d` is the first item dispatched end-to-end with that credential
path in place.

## Relation to Tier-2 Proof Sequence

| Item | What it proved |
|---|---|
| `livespec-impl-beads-ctq` | Dispatch → sandbox clone → implement → janitor → branch push |
| `livespec-impl-beads-5qv` | GH_TOKEN projection into sandbox env table |
| `livespec-impl-beads-w9d` | PR creation and merge from inside the container (this item) |
