# Plan-session lessons from the fabro-currency direction review (2026-10-10)

Three operating notes a plan session needs before it proposes a direction,
files a child, or spins up a reviewer. They are repo-additive guidance in
the sense of AGENTS.md §"Progressive guidance"; the maintainer rule in the
first section was declared in conversation on 2026-10-10.

## Route by the goal, not by prior ledger text (maintainer-declared 2026-10-10)

Three proposals in one plan session were rejected in a row: forking Petri
for a per-run resource limit before asking whether the limit was needed;
closing upstream PR 576 before measuring that the candidate engine has no
OTLP code and that the ratified contract consumes the spans; and routing a
rewrite to a third plan because a 2026-10-08 disposition line named it.
Each came from repeating text already on the ledger (a disposition, a scope
event, an item status) instead of from the standing goals (stay current on
Fabro, carry only what the factory needs, contribute upstream, own our
compute) and from source measurements. Prior ledger text records what an
earlier session believed; all three lines were wrong.

Before proposing a direction, state in one sentence which goal it serves
and name the measurement that supports it. Treat a disposition or scope
line as a claim to re-verify, never as routing. When the maintainer asks
"why do we need X", answer the need first, then the mechanism. When more
than one plan is in scope, say which plan owns each piece every time.

The independent review that caught the rest is the pattern to repeat: a
summary of the direction written to a file, a read-only Codex reviewer on
the newest model asked for omissions, holes and the big picture, and each
finding verified against source before it is adopted. Research note
`plan/fabro-currency/research/008-independent-review-and-corrections-2026-10-10.md`
is the worked example, including five findings that overturned claims the
session had already made to the maintainer.

## Spinning up a Codex reviewer in a herdr pane

"Astra" is OpenAI's `gpt-6-astra`; it is the default model in
`~/.codex/config.toml` on this host, but pass it explicitly. Measured
2026-10-10 on Codex CLI 0.162.1:

```bash
herdr pane split --current --direction right --cwd <repo> --no-focus   # returns pane_id, e.g. w6:p3
herdr agent start <name> --kind codex --pane w6:p3 --timeout 90000 -- -m gpt-6-astra --dangerously-bypass-approvals-and-sandbox
herdr agent prompt w6:p3 "$(cat brief.txt)"
herdr agent wait w6:p3 --until idle --timeout 2400000   # background it; returns when the agent is idle
herdr pane close w6:p3                                  # close the pane when its job is done
```

Give the reviewer a read-only brief with the exact source paths, ask for a
ranked critique written to a file plus a sentinel line, and close the pane
once the file is read: the maintainer asked "Why do you still have the
separate Codex pane open? Do you still need it?" after a replay pane sat
idle, and a later host replay must come from a freshly started session
anyway. `herdr agent get <name>` returns nothing once the pane is back at a
shell; `herdr pane list --workspace <ws>` shows the state, and
`herdr workspace list` maps workspace ids to labels (w6 is `fabro`).

## Plan-primitive gaps met while rewriting a ledger (plugin build a7a11fda01c0)

- `BeadsClient.update_issue` takes `description`, `status`, labels,
  `metadata`, `acceptance_criteria` and `notes`, and NO `title`. Retitle
  through the verb, `bd update <id> --title "..."`; inside a wrapped
  script a `subprocess` call inherits the wrapper's credentials.
- No primitive amends a plan epic's `## Definition of Done`. Rewrite the
  whole epic description with that section first (keep the
  `Plan anchor for plan/<slug>.` line), then record a scope event WITH
  `carriers=` mapping every assertion ordinal; without the carrier block
  the re-wording is unrecorded.
- `create_thread(project_root=...)` writes the research note and the
  anchor under `project_root`. Create the worktree first and pass its
  path, or the files land on the primary checkout.
- `apply_intake_dor` routes a factory-safe item to `pending-approval` and a
  host-routed one to `ready`; `drive --action impl:<id>` admits and
  dispatches a pending-approval item in one step.
- Write ledger scripts with idempotency markers (a comment carrying a
  marker string, checked before each mutation) so a partial run can be
  re-run without double-filing.
