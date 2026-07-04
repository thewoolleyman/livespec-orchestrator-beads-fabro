# Loop-reflection lessons (human-ratified)

This file is the **human-ratified** Reflexion-style lessons digest the
out-of-band reflector (work-item 29f.4) feeds and the orchestrator injects
into future dispatch briefs. Per the loop-reflection-gate design
(`best-practices-and-design.md` §7 decision 10), auto-injecting unreviewed
LLM lessons into every future brief is a prompt-injection-shaped risk and
dilutes briefs, so the improvement loop stays human-supervised, matching
the family's consent discipline.

## Ratification model — proposal → PR → merge

1. The reflector **proposes** a lesson by opening a PR that edits THIS file
   (the `LessonsProposer` seam — `GitPrLessonsProposer` in production:
   branch → commit → push → `gh pr create`; `RecordingLessonsProposer` in
   tests, so no real PR is ever opened hermetically).
2. A human **ratifies** the lesson by **merging that PR**. Reviewing the
   diff is the supervision gate.
3. Only the **committed (merged)** content of this file injects into
   dispatch briefs. The reflector NEVER auto-injects an unratified lesson;
   the brief-injection consumer reads ONLY the merged file.

A lesson that is not merged has no effect on any brief — an unreviewed
proposal sits in the PR queue until a human accepts or closes it.

## Lessons

_No ratified lessons yet. The reflector will propose additions via PR; a
human merges to ratify._
