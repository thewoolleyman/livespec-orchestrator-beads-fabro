# LAW: Post-Merge Janitor Sentinel

This note is the artifact for `livespec-impl-beads-law`.

## Purpose

`livespec-impl-beads-law` existed solely as a proof target for the final
W7 Tier-2 proof after PR #90 installed `mise` in the orchestrator image.

Its scope is intentionally doc-only: no production code, workflow
configuration, secrets, or runtime behavior changed.

## What It Proved

A fully containerized Fabro dispatch round-trip — from the
`livespec-orchestrator` production image (with `mise` installed by PR #90)
through sandbox clone, implementation, PR creation, merge, post-merge
primary refresh, and janitor completion — can execute end-to-end from
inside the production orchestrator container.

This item is the boundary condition that confirms the `mise`-in-container
installation landed in PR #90 is sufficient for the orchestrator to complete
the full dispatch lifecycle without missing toolchain dependencies.

## Relation to Tier-2 Proof Sequence

| Item | What it proved |
|---|---|
| `livespec-impl-beads-ctq` | Dispatch → sandbox clone → implement → janitor → branch push |
| `livespec-impl-beads-5qv` | GH_TOKEN projection into sandbox env table |
| `livespec-impl-beads-w9d` | PR creation and merge from inside the container |
| `livespec-impl-beads-law` | Post-merge primary refresh and janitor completion with mise installed in the production orchestrator image (PR #90) |
