---
topic: unrunnable-acceptance-visibility
author: codex-gpt-5.6-sol
created_at: 2026-09-12T10:36:15Z
---

## Proposal: Unrunnable acceptance is visible before dispatch

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Make the pre-dispatch acceptance-criteria wall part of the advertised dispatchability predicate and add a durable attention lane for already-filed rows that fail it. This prevents `next` and `needs-attention` from calling a ready item dispatchable when the Dispatcher will refuse it, while retaining the intentional human-only and groom-kind exemptions.

### Motivation

Plan epic livespec-n33rwg child .10 measured that description-level `## Acceptance` prose with an empty native acceptance-criteria field can sit in ready and be ranked as implementable even though the pre-dispatch wall refuses it. A 2026-09-12 audit of the owning orchestrator tenant found 16 already-filed ready items for which the shipped shared wall returns an ungradeable refusal; the sanctioned `next --limit 50` output nevertheless advertised all 16 among 38 candidates. The current contract explicitly leaves legacy rows to refuse on contact, so implementation alone cannot honestly close the visibility defect.

### Proposed Changes

Amend `SPECIFICATION/contracts.md` so every operator-facing dispatch-candidate enumeration MUST apply the same variant-aware acceptance eligibility decision as the pre-dispatch wall before advertising an `impl:<id>` action. A physically `ready` item whose effective acceptance policy is AI-dispositive and whose effective acceptance criteria resolve to zero gradeable assertions MUST NOT appear in `next` candidates, the `needs-attention` impl-next recommendation, the idle-factory first-dispatch handoff, or the Dispatcher drain candidate set. The decision MUST compose the single effective-criteria primitive and the same effective workflow-variant resolution as dispatch: a deliberate `human-only` policy clears the defect, and a groom-kind variant remains exempt because its purpose is to produce gradeable slices. Implementations MUST NOT introduce a second parser or a path-local approximation of eligibility.

Replace the current `left to refuse on contact` treatment for already-filed rows with a read-only audit surface. `needs-attention` MUST emit one stable hygiene fact per already-filed item that is physically ready yet fails the shared variant-aware acceptance eligibility decision. The fact MUST identify the item as `UNRUNNABLE`, carry the effective-criteria source and gradeable-assertion count, name authoring criteria via groom/edit or deliberately selecting `human-only` as the remedies, and MUST NOT carry an `impl:<id>` handoff the Dispatcher would reject. A human-only item and a groom-kind item MUST NOT produce this fact. The fact MUST clear when the same item gains gradeable criteria, changes to a deliberately human-only policy, selects an exempt groom-kind variant, or leaves the relevant lane.

The `next` contract's candidate-set and pagination totals MUST be defined over dispatch-eligible ready items after this refusal filter, not all physical ready rows. Any shared ranker used by `next`, `needs-attention`, idle-factory detection, and the Dispatcher drain MUST receive or compose the same eligibility authority so those surfaces cannot disagree about the first dispatchable item. A hand-picked explicit dispatch remains refused with exit 5 and its existing detailed error; this proposal changes earlier visibility, not that safety wall.

Add a new `SPECIFICATION/scenarios.md` scenario with discriminating controls: an already-filed ready AI-dispositive item with zero gradeable assertions is absent from `next`, is not emitted as impl-next or idle-factory executable work, and appears as one UNRUNNABLE hygiene fact without an executable dispatch handoff; an otherwise identical `human-only` item remains dispatchable and produces no defect fact; an ungradeable groom-kind item remains eligible; and adding a gradeable criterion makes the defect fact clear and the item appear exactly once in every candidate surface. During revise, the resulting-files payload MUST update `tests/heading-coverage.json` atomically for the new scenario heading and bind it to an integration-tier test.
