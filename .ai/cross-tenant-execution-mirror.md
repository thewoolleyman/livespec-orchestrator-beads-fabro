# Cross-Tenant Execution Mirror

This note records the operational convention for a work-item whose tenant repo
differs from the repo that must receive the implementation.

## Limitation

The Dispatcher sandboxes the `--repo` tenant repo. It does not provide per-item
repo targeting, so an item filed in one tenant cannot natively stage or publish
changes against a different implementation repo.

The live instance was `livespec-bhqt` work routed to
`livespec-dev-tooling-72r5`: the implementation landed through PR #544 in the
implementation repo, while the original tenant item remained the epic-graph
anchor.

## Decision

On 2026-07-23, under supervisor decision by maintainer delegation for the
approved `bd-ib-cvgjop` grooming cut, the execution-mirror convention became the
documented answer for this limitation. Native cross-repo staging is deliberately
unbuilt: the observed failure data does not justify engine work, and codifying
this convention does not foreclose later native support.

## Convention

1. File an `EXECUTION` mirror item in the implementation repo's own tenant. The
   mirror carries the same scope and acceptance criteria as the original item and
   cross-references the original tenant item.
2. De-arm the original item as the epic-graph anchor through the drive valves.
   Never hand-edit labels to do this.
3. Journal on both items. After the mirror's merge is verified, close the
   original anchor as `answered-by-convention`.
