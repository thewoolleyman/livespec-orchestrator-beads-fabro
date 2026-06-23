---
topic: orchestrate-operator-ux
author: claude-opus-4-8
created_at: 2026-06-22T23:10:44Z
---

## Proposal: orchestrate operator-surface ergonomics: interactive walkthrough, cwd-default --repo, Markdown-default output

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Refine the `orchestrate` operator surface contract under contracts.md §"The eight-skill surface" → "Operator skill (1)" → `orchestrate` so the everyday operator path stops requiring boilerplate: a bare `orchestrate` invocation (no subcommand) MUST present an interactive operator walkthrough that lists the available actions and lets the operator select one (composing the same read-only plan → select → run flow); `--repo` MUST default to the current working directory's repo when omitted (still overridable); and console output MUST be human-readable Markdown by default, with `--json` as the explicit machine-readable opt-in. Everything else about the operator contract is preserved: `plan` stays read-only, `run` dispatches only selected impl actions through Dispatcher/Fabro, spec actions return human handoffs and never mutate spec state, the surface creates no net-new work-items, and it does not duplicate ranking logic from either `next` surface.

### Motivation

The current contract REQUIRES a subcommand (`plan` / `run`), REQUIRES `--repo` on each, and treats `--json` as the implicit shape every documented invocation passes (`plan --repo <path> --json`). For an operator working inside a governed repo this is pure ceremony: the repo is almost always the cwd, the everyday read is human-facing not machine-facing, and a bare `orchestrate` should help rather than error on a missing subcommand. The maintainer wants the operator surface to default to the ergonomic path — walk me through the choices, assume this repo, show me Markdown — while keeping the explicit `plan`/`run` + `--repo` + `--json` forms available for scripts, CI, and the Dispatcher.

### Proposed Changes

Amend `SPECIFICATION/contracts.md` within the existing `#### `orchestrate`` subsection (under the `## The eight-skill surface` H2 → `### Operator skill (1)` H3). No H2/H3/H4 headings are added, removed, or renamed; all edits are to the prose, the `CLI surface:` list, and the `Operator procedure:` list inside that subsection.

1. CLI surface list — replace the two-line list:

```
- `orchestrate plan --repo <path> [--json]`
- `orchestrate run --repo <path> --action <action-id> [--json]`
```

with a list that documents the bare form and makes `--repo`/`--json` optional:

```
- `orchestrate` (no subcommand) — interactive operator walkthrough.
- `orchestrate plan [--repo <path>] [--json]`
- `orchestrate run [--repo <path>] --action <action-id> [--json]`
```

2. Add a new normative paragraph immediately after the CLI surface list, before `Operator procedure:`, codifying the three ergonomic defaults as MUST clauses:

```
Three operator-surface defaults shape the everyday path; each has an
explicit override so scripts, CI, and the Dispatcher keep a fully
specified invocation:

- **Bare `orchestrate` — interactive walkthrough.** Invoked with no
  subcommand, `orchestrate` MUST present an interactive operator
  walkthrough rather than erroring on a missing subcommand. The
  walkthrough composes the same read-only `plan` → select → `run`
  flow: it runs `plan` against the resolved repo, presents the
  returned `actions[]` for the operator to choose from, and on a
  selection invokes the equivalent `run` for that action id. It MUST
  NOT introduce any new selection or ranking logic — it is a
  presentation layer over `plan` and `run`. The explicit `plan` and
  `run` subcommands remain available unchanged for non-interactive
  callers.
- **`--repo` defaults to the current repo.** When `--repo` is
  omitted, the surface MUST default the target repo to the current
  working directory's repo (the governed checkout the operator is
  in). `--repo <path>` remains accepted and overrides the default.
  Resolution failure (the cwd is not inside a governed repo, or the
  resolved path does not exist) MUST surface a precondition error
  (exit 3) naming the unresolved path, as today.
- **Markdown output by default; `--json` is the machine opt-in.**
  Console output MUST default to human-readable Markdown. `--json`
  is the explicit opt-in to machine-readable JSON output; the
  Dispatcher-facing and CI-facing invocations continue to pass
  `--json` for stable parsing. The JSON payload shape (the
  `actions[]` plan from `plan`; the dispatch/handoff envelope from
  `run`) is unchanged — only the default rendering flips from JSON
  to Markdown.
```

3. Operator procedure list — update the existing numbered steps so the explicit-invocation examples no longer imply `--json` is mandatory, and add the bare-walkthrough form. Replace:

```
Operator procedure:

1. Invoke `plan --repo <path> --json`.
2. Present the returned `actions[]` to the human operator.
3. Invoke `run --repo <path> --action <action-id> --json` only for the
   selected action id.
4. Summarize the result, including `status`, Dispatcher exit code,
   parsed Dispatcher JSON when present, stderr when non-empty, PR/run
   fields when present, and any spec-side handoff command.
```

with:

```
Operator procedure (interactive form): invoke bare `orchestrate`; it
runs `plan` for the resolved repo, presents the `actions[]`, and on a
selection runs the equivalent `run` and summarizes the result.

Operator procedure (explicit form):

1. Invoke `plan [--repo <path>] [--json]`.
2. Present the returned `actions[]` to the human operator.
3. Invoke `run [--repo <path>] --action <action-id> [--json]` only for
   the selected action id.
4. Summarize the result, including `status`, Dispatcher exit code,
   parsed Dispatcher JSON when present, stderr when non-empty, PR/run
   fields when present, and any spec-side handoff command.
```

4. The non-Claude-runtime fallback paragraph at the end of the subsection currently reads `... plan --repo <path> --json` and `... run --repo <path> --action <action-id> --json`. Leave those literal fallback examples as fully-specified invocations (machine callers SHOULD pass `--repo` and `--json` explicitly), but add one sentence noting that the same defaults (cwd `--repo`, Markdown-without-`--json`, bare-`orchestrate` walkthrough) apply uniformly to direct Python CLI invocation — the defaults are a property of the CLI, not of the Claude skill binding.

## Proposal: Scenario: orchestrate operator-surface defaults (walkthrough, cwd --repo, Markdown default)

### Target specification files

- SPECIFICATION/scenarios.md
- ../tests/heading-coverage.json

### Summary

Add a Gherkin scenario to scenarios.md (`## Scenario 17 — orchestrate operator-surface defaults`) that pins the three observable behaviors introduced by the contracts.md refinement: a bare `orchestrate` invocation presents an interactive walkthrough instead of erroring on a missing subcommand; an omitted `--repo` resolves to the current working directory's repo; and console output is Markdown by default with `--json` flipping it to JSON. Co-edit `tests/heading-coverage.json` to register the new H2 with a `TODO` test binding, matching the baseline-backfill pattern used for the other operator-surface and Dispatcher scenarios.

### Motivation

The three refinements are load-bearing, observable behaviors (an input → output and an error-path change), so per the propose-change authoring discipline §"Behavior ⇒ Gherkin scenario" they MUST be carried by a `## Scenario` in scenarios.md, not by contracts.md prose alone. There is currently no scenario covering the orchestrate operator surface at all; this adds the first one and keeps the heading-coverage map in lockstep per the self-application co-edit rule.

### Proposed Changes

Two co-edited files.

(A) `SPECIFICATION/scenarios.md` — append a new H2 scenario after the existing `## Scenario 16 — Closed-item-integrity check rejects "closed but unproven"` block (it is the last scenario in the file):

```
## Scenario 17 — orchestrate operator-surface defaults

```gherkin
Feature: orchestrate operator surface defaults to the ergonomic path
  As an operator working inside a governed repo
  I want bare `orchestrate`, a cwd-default repo, and Markdown output
  So that the everyday cross-side selection loop needs no boilerplate
  while scripts and the Dispatcher keep a fully specified invocation

Scenario: A bare orchestrate invocation walks the operator through the choices
  Given a governed repo whose spec-side and impl-side `next` surfaces are reachable
  When the operator invokes `orchestrate` with no subcommand
  Then the surface presents an interactive walkthrough of the available `actions[]`
  And it does NOT error on a missing subcommand
  And selecting an action composes the same read-only plan -> select -> run flow without introducing new ranking logic

Scenario: An omitted --repo resolves to the current working directory's repo
  Given the operator's current working directory is inside a governed repo
  When the operator invokes `orchestrate plan` without `--repo`
  Then the surface resolves the target repo to that current-directory repo
  And an explicit `--repo <path>` still overrides the default when supplied

Scenario: Console output is Markdown by default and JSON only with --json
  Given any `orchestrate plan` or `orchestrate run` invocation
  When the operator omits `--json`
  Then the surface renders human-readable Markdown
  And passing `--json` renders the same payload as machine-readable JSON
```
```

(B) `tests/heading-coverage.json` — add one entry registering the new H2, mirroring the existing scenario entries' shape and the `TODO`-test baseline-backfill convention:

```
  {
    "heading": "## Scenario 17 — orchestrate operator-surface defaults",
    "spec_root": "SPECIFICATION",
    "spec_file": "scenarios.md",
    "test": "TODO",
    "reason": "Added by the orchestrate-operator-ux revise pass. The scenario pins the three orchestrate operator-surface defaults (bare-invocation walkthrough, cwd-default --repo, Markdown-default output with --json opt-in). A real integration-tier test id is populated by the governed propose-change/revise loop's resulting_files[] mechanism once the operator-surface ergonomics gain an exercising test (alongside the follow-up impl work-item that implements them)."
  }
```

Insert this object into the existing top-level JSON array (the file is a flat array of heading objects); placement is anywhere in the array — grouping it near the other `scenarios.md` entries is preferred but not required, since the heading_coverage check matches on the heading/spec_file pair, not array order. The path is spelled `../tests/heading-coverage.json` in `target_spec_files` so the wrapper's `spec_target / path` join resolves it to the project-root `tests/heading-coverage.json`.
