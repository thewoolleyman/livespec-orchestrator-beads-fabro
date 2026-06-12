# scenarios.md — livespec-impl-beads

End-to-end behavioral narratives illustrating the plugin's intended use
across the workflow loops defined in `livespec/SPECIFICATION/`. These
are not test cases (those live under `tests/`); they are reader-facing
journeys an agent or contributor follows.

## Scenario 1 — Gap-tied fix cycle

A consumer project has a fresh `livespec` revision (vNNN+1) that
introduced a new MUST clause not yet honored in the impl.

1. The user invokes `/livespec-impl-beads:capture-impl-gaps`. The skill
   loads the rule set via the Spec Reader, walks each rule against the
   impl, and surfaces uncaptured gaps one at a time.
2. For each gap the user consents to file, the skill creates a beads
   issue via `bd create` carrying the `origin:gap-tied` and
   `gap-id:<stable-id>` labels, `status: open`, and the user-confirmed
   title / description.
3. The user invokes `/livespec-impl-beads:next`. The ranker reads the
   materialized work-items back from `bd` and surfaces the newly-filed
   gap-tied item as the recommendation (gap-tied beats freeform at equal
   priority).
4. The user invokes `/livespec-impl-beads:implement` for that work-item.
   The skill walks Red → Green → closure.
5. At closure, the skill re-runs `capture-impl-gaps` in dry-run mode and
   confirms the `gap_id` is no longer detected. On success, it closes
   the issue IN PLACE: `bd close --reason …`, `bd update` to set the
   `resolution:completed` label, and the `AuditRecord`
   (`verification_timestamp`, `commits`, `files_changed`, `merge_sha`,
   optional `pr_number`) written into the issue's `metadata` column.

## Scenario 2 — Memo → spec-bound disposition

The user notices something during impl work that doesn't fit the current
work-item but is intent-bearing.

1. The user invokes `/livespec-impl-beads:capture-memo` and types a
   one-paragraph observation. The skill creates a beads issue carrying
   the `kind:memo` and `state:untriaged` labels and a fresh `id`.
2. Later, the user invokes `/livespec-impl-beads:process-memos`. The
   skill iterates over untriaged memos and asks for a disposition per
   memo.
3. For this memo, the user picks `spec-bound`. The skill hands off to
   `/livespec:propose-change` with the memo content as the
   proposed-change source; a new file lands under the consumer's
   `<spec-root>/proposed_changes/`.
4. The skill updates the memo issue IN PLACE: `state:untriaged` →
   `state:dispositioned` plus a `disposition:spec-bound` label, and
   records the resulting `propose_change_topic` in the issue's
   `metadata` column for cross-reference.
5. The next `/livespec:doctor` pass sees one fewer untriaged memo; if
   memo backlog was driving a memo-hygiene `warn`, the warning clears.

## Scenario 3 — Memo → persistent-knowledge graduation

The user has been re-discovering the same workflow gotcha across
sessions. A memo describing the gotcha exists.

1. The user invokes `/livespec-impl-beads:process-memos`.
2. For this memo, the user picks `persistent-knowledge`. The skill asks
   for a topic name (e.g., `mise-exec-for-git-hooks`).
3. The skill writes the memo content to
   `.ai/mise-exec-for-git-hooks.md` (creating the file if absent).
4. The skill verifies `CLAUDE.md` (and/or `AGENTS.md`) references that
   file via a bullet; if not, it adds the reference.
5. The skill updates the memo issue IN PLACE: `state:dispositioned`
   plus `disposition:persistent-knowledge`, and records
   `knowledge_file: ".ai/mise-exec-for-git-hooks.md"` in the issue's
   `metadata` column.
6. Future sessions load that knowledge file on demand via the harness's
   `CLAUDE.md` / `AGENTS.md` reference traversal.

## Scenario 4 — Freeform bug fix

The user spots a bug unrelated to any open gap.

1. The user invokes `/livespec-impl-beads:capture-work-item` and
   supplies title, description, `type: bug`, `priority: 2`. The skill
   creates a beads issue carrying the `origin:freeform` label and no
   `gap-id:` label.
2. The user invokes `/livespec-impl-beads:implement` for that item.
   Red → Green proceeds normally.
3. At closure, the skill takes the freeform path: close the issue IN
   PLACE with `resolution:completed` and the user-supplied `--reason`
   (`bd close --reason`, `bd update` for the resolution label). No
   `gap_id` re-detection runs.

## Scenario 5 — Doctor cross-boundary read

The user invokes `/livespec:doctor` in a consumer project.

1. Doctor's static phase reads `<spec-root>/` directly.
2. Doctor's cross-boundary phase invokes the active impl-plugin's
   thin-transport query skills:
   - `/livespec-impl-beads:list-memos --filter=untriaged --json` for the
     memo-hygiene invariant.
   - `/livespec-impl-beads:list-work-items --json` for the four
     work-item structural invariants.
3. Each invocation reads the tenant DB through `bd` and MUST complete
   deterministically with the contract-mandated JSON schema. A missing
   or malformed plugin surface fires a `fail` finding (no silent skips).
   In hermetic / CI contexts the in-memory fake backend stands in for a
   live tenant DB and satisfies the same schema.

## Scenario 6 — Cross-repo Layer 3 loop driver (livespec-resident)

Cross-reference: cross-side composition of impl-side `next` with
spec-side `/livespec:next` is a Layer 3 (project-local orchestration)
concern per `livespec/SPECIFICATION/spec.md` §"Three-layer
orchestration architecture" → "Cross-side composition belongs at
Layer 3". This scenario describes the Layer 3 driver's behavior; this
plugin's `next` skill itself ranks impl-side state only and MUST NOT
bake a cross-side weighting in.

livespec's `.claude/skills/livespec-orchestrate/SKILL.md` is the
livespec-resident cross-repo orchestration driver. At the top of each
iteration:

1. The driver invokes `/livespec:next --json` to get a spec-side
   recommendation.
2. The driver invokes `/livespec-impl-beads:next --json` to get an
   impl-side recommendation.
3. The driver composes the two outputs into a per-iteration action plan
   per the orchestration-layer rules defined in
   `livespec/SPECIFICATION/`.
4. **Empty-queue handoff.** When both `/livespec:next` and
   `/livespec-impl-beads:next` emit empty `candidates: []` arrays (the
   no-work signal on both sides), the Layer 3 driver SHOULD offer the
   user a hygiene fallback — at minimum, a `/livespec:doctor` pass and a
   `/livespec:critique` pass — and MAY also offer
   `/livespec:prune-history` if `next.prune_history_threshold` would
   otherwise have suppressed it. The hygiene fallback is a Layer 3
   productivity heuristic per the upstream `Durable-pending` doctrine;
   it is NEVER baked into the Layer 2 `next` emission itself.

Memo, gap-detection, and drift-detection invocations
(`/livespec-impl-beads:process-memos`,
`/livespec-impl-beads:capture-impl-gaps`,
`/livespec-impl-beads:capture-spec-drift`) are likewise Layer 3
driver-side concerns that the driver invokes outside of `next`'s
ranking — `next` ranks materialized work-items only (the canonical
actionable-memo probe is `list-memos --filter=untriaged`).

This plugin is responsible only for step 2's output schema and behavior;
the composition rules and empty-queue handoff policy are entirely in
scope for `livespec` and the project-local driver, not for this spec.
