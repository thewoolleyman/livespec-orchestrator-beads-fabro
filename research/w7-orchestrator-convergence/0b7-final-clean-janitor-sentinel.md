# 0B7: Final Clean Janitor Sentinel

This note is the artifact for `livespec-impl-beads-0b7`.

## Purpose

`livespec-impl-beads-0b7` existed solely as a proof target for the final
W7 Tier-2 proof after PR #94 added `libatomic1` to the orchestrator image.

Its scope is intentionally doc-only: no production code, workflow
configuration, secrets, or runtime behavior changed.

## What It Proved

A fully containerized Fabro dispatch round-trip — from the
`livespec-orchestrator` production image through sandbox clone,
implementation, PR creation, merge, post-merge primary refresh, fresh
janitor checkout, janitor success, and clean dispatcher exit — can execute
end-to-end from inside the production orchestrator container after
`libatomic1` was added to the image by PR #94.

This is the boundary condition that confirms the `libatomic1` addition in
PR #94 is sufficient for the orchestrator to complete the full dispatch
lifecycle through dispatcher exit without leaving dirty or unresolvable
state.

## Relation to Tier-2 Proof Sequence

| Item | What it proved |
|---|---|
| `livespec-impl-beads-ctq` | Dispatch → sandbox clone → implement → janitor → branch push |
| `livespec-impl-beads-5qv` | GH_TOKEN projection into sandbox env table |
| `livespec-impl-beads-w9d` | PR creation and merge from inside the container |
| `livespec-impl-beads-law` | Post-merge primary refresh and janitor completion with mise installed in the production orchestrator image (PR #90) |
| `livespec-impl-beads-uw8` | Clean dispatcher exit after PR creation, merge, post-merge primary refresh, fresh janitor checkout, and janitor success with writable proof checkout (PR #92) |
| `livespec-impl-beads-0b7` | Full dispatch lifecycle through clean dispatcher exit with libatomic1 in the production orchestrator image (PR #94) |
