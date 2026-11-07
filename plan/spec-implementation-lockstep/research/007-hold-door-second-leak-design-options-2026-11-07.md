# The hold door's second leak: design options for the maintainer (2026-11-07)

Written by plan session spec-implementation-lockstep (session 633d1b75) on the order of legacy-coordinator-agent (session 8e04c5e0, R301). The coordinator ruled this an architectural, multi-repository decision that belongs to the maintainer (coordinator duties §9). It asked for one note with the options, their costs, a recommendation and the reviewer's verified findings, and then a stop. No proposal is filed and no implementation is started. The work item that waits on this decision is bd-ib-x366dh: "The spec-change tier classification also judges against the ratified specifications of repositories that govern this one, and holds a bug, chore or non-functional item that would break a MUST". It stays held and marked DO NOT APPROVE.

## Notation used in this note

- **Spec-change tier, and the hold.** Every implement-kind work item is classified at filing, at groom and on every dispatch path. A `feature` whose asked-for behaviour the specification does not state (verdict `partial` or `unstated`) is "spec-change tier". It is *held*: it may not be built until a linked proposed change ratifies. contracts.md §"Grooming and slice-size calibration", autonomy-tier bullet.
- **Classification.** One model call that names the item's class: `feature`, `bug`, `chore` or `non_functional`. It is made by `classify` in `livespec_runtime.spec_stated`, the shared module both orchestrators vendor.
- **Verdict.** A second model call, `judge`, that is made only for a `feature`. It reads a condensed copy of the specification and answers `stated`, `partial` or `unstated`.
- **The non-feature exemption.** The ratified rule: "An item classified `bug`, `chore` or `non_functional` is never spec-change tier." Scenario 206 states the intent: "bugs and chores keep their leeway".
- **Governing specification.** A specification other than the governed repository's own whose clauses still bind its behaviour. For this repository that means livespec-dev-tooling's, whose commit hooks and gates it runs, and livespec core's.
- **The two leaks in the hold door.** First, the `approve` valve never reads the hold, so a held item can be pressed into `ready`. That leak is bd-ib-bomy33, already filed and ready. Second, the subject of this note: work that changes stated behaviour is not held at all.

## What happened

bd-ib-yqjaut ("A janitor refresh merge runs the full suite once on the merged tree") was filed at 2026-11-07T22:30:05Z. Its tier record reads tier `none`, classification `non_functional`, verdict not taken, so it routed to `ready`. Only a hand-written HOLD comment from its owner, sandbox-commit-gate-ceiling, keeps it from dispatch.

Its owner has since measured that the change needs two spec changes. One is in livespec-dev-tooling: `livespec-dev-tooling-z5fwwn` must ship. The other is an amendment to THIS repository's own contracts.md paragraph "The run refreshes before the janitor" and Scenario 305. The measurement was taken on bd-ib-hap62u run 01M6VBZF4371, janitor@3: a refresh `git merge` fires only the commit-msg hook, never pre-commit.

## Two gaps, verified in source on build 1895a0ddbe37

1. **The exemption.** `commands/_spec_change_tier_gate.py` records a non-feature as tier `none` immediately after classification and takes no verdict. That conforms to the ratified rule, so this is a rule to amend, not a defect to fix. It is the gap that let bd-ib-yqjaut through, and it would have done so even with no other repository involved, because the clause the item needed changed is in this repository's own spec.
2. **Scope.** The classifier reads only this repository's `SPECIFICATION/`, so no clause of a governing specification is ever in view. That would matter for an item whose only conflict is with livespec-dev-tooling's or livespec's clauses.

## The independent review

A read-only reviewer (Codex gpt-6.1-sol) was given this session's first direction and the source of this repository, livespec-dev-tooling, livespec-runtime and livespec-orchestrator-git-jsonl. Its verdict was "adopt with named changes", with eleven findings; the full report is `data/007-review-codex-gpt-6.1-sol.md` beside this note.

Verified by this session against source:

- **Finding 2.** The classification prompt carries only the title, the description and the stored type (`CLASSIFY_PROMPT`, vendored `livespec_runtime/spec_stated.py:100-119`), and `classify()` takes no specification input. So detecting a broken MUST cannot be added to the classification as a "wider reply": every classification would have to receive spec text.
- **Finding 9.** livespec-dev-tooling v1.187.0 contracts.md:561, "Same-tree reuse", already lets a commit reuse a passing full pre-commit run on the same tree. That reframed bd-ib-yqjaut, and its owner has chosen a conforming route on it.
- **Finding 10.** A non-feature tier record is written without its selected clauses but marked complete, so reuse never matches and every dispatch path classifies it again. Filed as bd-ib-ax6bxj, ready, class bug. livespec-orchestrator-git-jsonl does not share it, because it classifies once at filing and has no reuse path.

Taken on the reviewer's own probe, not re-run here:

- **Finding 3.** Combining this repository's spec with livespec-dev-tooling v1.187.0's and livespec v0.45.1's (17 files, about 3.17 million characters) under today's prompt ceiling selected ZERO complete clauses for the bd-ib-yqjaut statement, against 24 from this repository alone. Every heading is kept before any body budget is spent, so the heading list alone uses up the ceiling.

Further findings, which were not verified here and which any option crossing a repository boundary must answer:

- The shared record shape has no conflict field (livespec-runtime contracts.md:946-955).
- git-jsonl's codec requires a spec-change record to carry a `partial` or `unstated` verdict.
- Clause identity is a bare heading string, and real headings repeat across repositories ("Lifecycle", "Boundary", "Versioning").
- A hold on another repository's clause has no proposal, ratification and pin-adoption path to release it.
- An unreadable governing specification needs its own outcome, rather than silently admitting the item.

## Volume and cost basis

Items created in the seven days to 2026-11-07, by stored type, which is only a proxy for the judged class:

| Tenant | bug | task | feature | chore | per day |
|---|---:|---:|---:|---:|---:|
| this repository | 180 | 80 | 56 | 4 | about 46 |
| livespec-dev-tooling | 137 | 88 | 72 | 1 | about 43 |

That is about 70 non-feature filings a day. A spec-reading host judgement costs about $0.11 today uncached (token-spend-analysis, 2026-11-07), because prompt caching is off for host judges (c628a589c). Classification alone, with no spec text, is far cheaper.

## Options

**A. Status quo plus hand holds.** Keep the exemption and rely on a filer or plan session writing a HOLD comment, as on bd-ib-yqjaut. Cost: none. It is not machine-enforced, and it leaks whenever nobody notices. bd-ib-bomy33 still closes the `approve` half of the door.

**B. Take the existing verdict for non-features, own specification only.** For a `bug`, `chore` or `non_functional` item, also run today's `judge` against this repository's own specification. Hold it when the verdict is `partial` or `unstated` AND a narrowly worded condition holds: the item's requested resulting behaviour would contradict a binding clause. That condition is the reviewer's smallest defensible Scenario 206 amendment, its finding 11. No new verdict kind and no cross-repository machinery.
- Cost: about 70 extra spec-reading calls a day at filing, about $8 a day uncached, plus a retake per changed input once bd-ib-ax6bxj fixes reuse.
- Risk: today's verdict answers "is this stated?", not "does this break a MUST?". So without measured controls it may over-hold performance and cleanup work, or mistake a bug fix that RESTORES a clause for one that breaks it.
- It would have caught bd-ib-yqjaut, whose conflict was in this repository's own Scenario 305, but only if the verdict reads that as partial or unstated. That has not been measured.

**C. A combined class, coverage and conflict judgement in livespec-runtime, own specification only.** Replace `classify` plus `judge` with one shared judgement that receives spec text and reports the class, the coverage verdict and any binding clause the requested outcome would break, with a quote. This is a public-contract and versioning change to livespec-runtime. Both orchestrators' record codecs change, and old records need a migration policy.
- Cost: one spec-reading call per item instead of a cheap classification plus a judge call for features, so the totals need measuring. It is several sessions of work across three repositories.
- It answers the right question directly, and the reviewer's finding 11 lists the controls it would need to be trusted.

**D. Option C plus governing repositories' specifications.** Everything in C, plus each repository naming the specifications that govern it and the classification reading them at the pinned release. The pins: livespec-dev-tooling and livespec-runtime through `pyproject.toml` plus `uv.lock`, and livespec core through `.livespec.jsonc`'s compat pin; not `.mise.toml` or `.copier-answers.yml`. It also needs a targeted retrieval with a measured recall control, since finding 3 shows that pooling fails, plus repository-qualified clause identity and applicability, a foreign proposal and pin-adoption release path, and an unreadable-governing-spec outcome.
- Cost: the largest; a multi-session design across livespec-runtime, both orchestrators and every adopting repository.
- It is the only option that holds an item whose sole conflict is with another repository's clause.

## Recommendation

1. Measure first, for about $5 to $10 and no contract change. Run today's `judge` offline against this repository's own specification over the last 50 non-feature filings plus bd-ib-yqjaut. Hand-label each as "would break a stated clause" or not, and count true holds, false holds and misses. That decides between B and C on evidence. It matches this plan's working method of costing a new mechanism for the whole fleet before endorsing it (`.ai/plan-session-lessons.md`).
2. Then adopt B if the existing verdict separates the two groups well enough, otherwise C. Either way, amend Scenario 206 and the autonomy-tier bullet together, wording it as a deliberate narrowing of the bug and chore leeway, because editing the scenario alone leaves the rule's exemption in force.
3. Defer D until a measured instance shows an item whose ONLY conflict is with another repository's specification. bd-ib-yqjaut turned out to need this repository's own spec changed, so it does not show that.
4. Meanwhile, land bd-ib-bomy33 (the approve-valve half) and bd-ib-ax6bxj (reuse). Both are filed, ready and independent of this decision.

## What this note does not decide

It files no proposal and changes no specification. It does not release or re-route bd-ib-yqjaut, which its owner is handling, or bd-ib-x366dh, which stays held. The volume figures use stored type, not judged class. The reviewer's unverified findings are listed so the decision accounts for them, not adopted as fact.
