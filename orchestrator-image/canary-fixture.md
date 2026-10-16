# Factory canary — record one line in the committed canary marker file

Everything in this file is work-item text. The first line is the canary
work-item's title; every line below it is the canary work-item's description,
verbatim, and that description's first heading is its Definition of Done. No
line of this file explains the file — that belongs to the runbook section
"Taking a candidate canary" — because a filed canary must read as the brief it
is, not as a brief wrapped in commentary about where it came from.

This is a CANARY. Its purpose is to exercise this repository's factory end to
end on a candidate engine, so its deliverable is deliberately the smallest
change this repository has: one added line in
`orchestrator-image/canary-marker.md`, the dedicated marker file kept for
exactly that purpose. Append one line under that file's
`## Recorded canary dispatches` heading naming this canary dispatch, and change
nothing else — no product code, no configuration, no other document.

Why that one line is the right assertion to grade, rather than anything about
the engine: the referenced scenario's closing clause is that a coherent
Definition of Done proceeds to the implement node. The added line is the
observable consequence of that clause holding. A dispatch that records the line
is a dispatch whose Definition-of-Done gate admitted the brief and whose
implement node then ran, and a dispatch that records no line is one that did
not — which is exactly what a canary is taken to find out.

## Definition of Done

- The file `orchestrator-image/canary-marker.md` carries one added line under its `## Recorded canary dispatches` heading naming this canary dispatch.

References: ## Scenario 131 — The Definition of Done gate admits a coherent item, refuses a malformed one host-side, and rests an incoherent one at needs-human
