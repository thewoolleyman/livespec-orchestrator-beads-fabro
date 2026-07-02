# EF5: Final Clean Dispatcher Sentinel

This note is the artifact for `livespec-impl-beads-ef5`.

## Purpose

`livespec-impl-beads-ef5` existed solely as a proof target for the final
W7 Tier-2 acceptance proof after PR #97 stabilized the post-merge janitor
coverage gate.

Its scope is intentionally doc-only: no production code, workflow
configuration, secrets, or runtime behavior changed.

## What It Proved

A fully containerized Fabro dispatch round-trip — from the
`livespec-orchestrator` production image through sandbox clone,
implementation, PR creation, merge, post-merge janitor execution, clean
dispatcher exit, and no stale checkout left on master — can execute
end-to-end after PR #97 stabilized the post-merge janitor coverage gate.

This is the boundary condition that confirms the cost-gate journal test
stabilization in PR #97 is sufficient for the orchestrator to complete the
full dispatch lifecycle — create a PR, merge it, run the post-merge janitor,
close with no stale checkout, and leave master clean.

## Relation to Tier-2 Proof Sequence

| Item | What it proved |
|---|---|
| `livespec-impl-beads-ctq` | Dispatch → sandbox clone → implement → janitor → branch push |
| `livespec-impl-beads-5qv` | GH_TOKEN projection into sandbox env table |
| `livespec-impl-beads-w9d` | PR creation and merge from inside the container |
| `livespec-impl-beads-law` | Post-merge primary refresh and janitor completion with mise installed in the production orchestrator image (PR #90) |
| `livespec-impl-beads-uw8` | Clean dispatcher exit after PR creation, merge, post-merge primary refresh, fresh janitor checkout, and janitor success with writable proof checkout (PR #92) |
| `livespec-impl-beads-0b7` | Full dispatch lifecycle through clean dispatcher exit with libatomic1 in the production orchestrator image (PR #94) |
| `livespec-impl-beads-6vo` | Clean dispatcher exit with no root-owned leftover files after cleaning root-owned janitor artifacts from the mounted primary checkout |
| `livespec-impl-beads-ef5` | Full dispatch lifecycle through clean dispatcher exit with no stale checkout after the post-merge janitor coverage gate was stabilized by PR #97 |
