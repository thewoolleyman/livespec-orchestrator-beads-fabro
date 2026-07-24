---
topic: supervisor-handoff-hosted-artifact-in-the-thread-store
author: claude-fable-5
created_at: 2026-07-24T12:16:04Z
---

## Proposal: The thread store MAY host one Control-Plane supervision artifact the plan operation ignores

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The `### The plan/<topic>/ thread store` contract describes `plan/<topic>/` as holding two facets (at most one handoff, zero or more research notes) and is now contradicted by live tracked state in a governed repo: `plan/rop-sweep-fleet-policy/supervisor-handoff.md` (livespec PR #1706), authored by the Control Plane's `supervise-plan` operation (livespec-overseer PR #49). This amendment admits the hosted artifact while keeping the two-facet model and the at-most-one-handoff refusal literally intact: the reserved `supervisor-handoff.md` is declared NOT a facet and NOT a handoff in this contract's sense (it resumes the supervising actor, never the thread's own work), and the `plan` operation MUST NOT create, read, or validate it — so the exception becomes enumerated rather than an accident of the `handoff*.md` refusal pattern not matching the name.

### Motivation

Slice 4 of the adopted supervise-plan design (livespec core `plan/plan-skill-supervisor-handoff/design.md` §11.3/§11.6, maintainer-adopted 2026-07-23): both upstream specs enumerate the planning thread's contents, so a third file contradicts them no matter who wrote it; the amendments are realization-agnostic declarations of non-ownership, deliberately filed AFTER the skill shipped and produced a real artifact so they describe something that exists. §4.2 of the same design specifically asks that the operation's refusal treat `supervisor-handoff.md` as the ONE named exception rather than an incidental glob miss. The sibling core amendment is filed as livespec PR #1724 (`SPECIFICATION/proposed_changes/supervisor-handoff-hosted-control-plane-artifact-in-plan-threads.md` there); this proposal is self-contained and does not depend on that one's ratification order.

### Proposed Changes

ONE edit to SPECIFICATION/contracts.md, §"The `plan/<topic>/` thread store": insert a new paragraph immediately AFTER the section's opening paragraph — the paragraph that begins with the byte-exact text "A planning thread is a first-class directory" and ends with the byte-exact text "(precedent: `loop-reflection-gate/`)." (each occurring exactly once in the file; verified against origin/master at filing time). The inserted paragraph reads:

**The hosted supervision artifact.** A planning-thread directory MAY additionally host at most one Control-Plane-authored artifact, at the reserved filename `plan/<topic>/supervisor-handoff.md`: the durable prompt for the actor SUPERVISING the thread's sessions. It is NOT a third facet and NOT a handoff in this contract's sense — it resumes the SUPERVISING actor, never the thread's own work — so the at-most-one-handoff rule and its refusal are unaffected, and `supervisor-handoff.md` is the enumerated exception rather than an incidental non-match of the `handoff*.md` refusal pattern. The `plan` operation MUST NOT create, read, or validate the file; a Control-Plane realization authors and maintains it through the repository's normal reviewed commit path. The artifact archives and unarchives with its thread.

Ratification co-edit (via the revise `resulting_files[]` mechanism, not a second proposal): `.claude-plugin/prose/plan.md` §"The planning-thread store" enumerates the same two facets and SHOULD gain a mirroring third bullet stating that the reserved `plan/<topic>/supervisor-handoff.md` MAY be present, is neither facet, and is never created, read, or validated by this operation.
