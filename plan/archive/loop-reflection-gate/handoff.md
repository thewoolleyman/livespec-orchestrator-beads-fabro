# loop-reflection-gate — handoff (CLOSED)

Thread state: **CLOSED / ARCHIVED** (2026-07-06). Epic
`livespec-impl-beads-29f` — "Reflection gate realization — Honeycomb-backed
eval/audit loop for the dispatcher" — is closed (`done` / `completed`); all
of its children have landed. This directory now lives under
`plan/archive/` per the thread lifecycle (a thread is active iff its epic
is open).

## Outcome

The reflection gate's eight built halves (mechanical loop-exit reflection
stage, telemetry enrich/scrub + receive planes, the out-of-band LLM
reflector with dedup filing, and the lessons PROPOSER) landed earlier. This
thread drove the remaining **lessons-injection CONSUMER** half, spec-first:

1. **Spec contract (2026-07-04)** — `/livespec:revise` landed SPECIFICATION
   v030: `contracts.md` "Dispatch-brief lessons injection" + Scenarios 39
   (ratified lesson injects) and 40 (unratified/absent/unmerged/unreadable
   never alter briefs). Sibling proposal `claude-fable-5-critique` also
   accepted (Scenario 41, no-root-research-tree invariant).
2. **Item update (2026-07-04)** — paired `livespec-impl-beads-29f.10` to the
   commitment `lessons-brief-injection-consumer` and cited the landed clauses.
3. **Grooming (2026-07-05)** — decomposed `.10` into two factory slices and
   regroomed the original out (`no-longer-applicable`).
4. **Implementation (2026-07-06)** — built directly via Red-Green-Replay
   (the Fabro factory was unavailable in the session environment):
   - **S1 `bd-ib-nznswb`** — `commands/_dispatcher_lessons.read_ratified_lessons`,
     the fail-open reader over the committed `loop-reflection-gate/lessons.md`.
     PR #325, closed `completed`.
   - **S2 `bd-ib-zwl7w3`** — `render_goal` gains a pure `lessons` param + the
     `_dispatch_one` host-side wiring (reads lessons from `repo`, like
     `comments`). PR #327, closed `completed`.
   - End-to-end verified on merged code: a ratified lesson reaches the brief's
     delimited "Ratified lessons" section (Scenario 39); a placeholder-only /
     absent file leaves the brief byte-identical (Scenario 40).

## Not part of this thread

- `bd-ib-umno37` (post-verdict remint hardening) — independent, `ready`; the
  factory drains it on its own. NOT a child of this epic.
- A follow-up is worth filing separately: the Dispatcher/Fabro subprocess did
  not find `fabro` on PATH in this environment (it is installed at
  `~/.local/bin/fabro`, not the configured `/usr/local/bin/fabro`), which
  blocked autonomous dispatch and forced the direct-implementation path above.

## Load-bearing note (unchanged)

The TOP-LEVEL `loop-reflection-gate/` directory (design-of-record + the
reflector's default `lessons.md` path) is LOAD-BEARING and is NOT this
archived `plan/archive/loop-reflection-gate/` thread directory — never
conflate or move the top-level one without a coordinated code change.
