# Canary marker

This file exists so that a factory canary has somewhere harmless to write.

It carries no product behaviour and nothing reads it but a human counting
canaries, which is the whole point: a one-line edit here is a change the
repository's check suite accepts without the canary having to touch any gated
surface. The canary that appends such a line is filed from
`orchestrator-image/canary-fixture.md` by `just canary-dispatch <factory>`;
the runbook section "Taking a candidate canary" in `orchestrator-image/README.md`
is the operator-facing route.

Do not put anything else in this file, and do not make any other file the
canary's target. A canary whose deliverable touches real product surface stops
being a measurement of the engine and becomes a measurement of the change.

## Recorded canary dispatches

- 2026-10-16 — marker introduced; no canary has recorded a line against it yet.
- 2026-10-17 — canary `bd-ib-d3h677` on factory `hp`, run `01M55GKWZ05JB53JTX14Q86597`.
- 2026-10-17 — `bd-ib-djbwai` on factory `hp-candidate`, run `01M55FJXTN15DR6DV85ZHBX00R`.
