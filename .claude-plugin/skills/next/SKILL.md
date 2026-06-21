---
name: next
description: Rank the most-ripe impl-side action from the beads-backed work-items store. Required thin-transport surface per livespec/SPECIFICATION/contracts.md §"Thin-transport skills (3) — required machine query surface". Pure function of file state; no LLM in the ranking path. Invoke as `/livespec-impl-beads:next [--limit <count>] [--offset <count>] [--json]`.
allowed-tools: Bash
---

# next

Thin-transport pass-through. All behavior lives in
`.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/next.py`.

## Invocation

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/bin/next.py" "$@"
```

Supported flags:

- `--limit <count>` — positive integer, default `5`. Maximum number
  of candidates returned in the `candidates` array. Non-positive
  values cause the wrapper to exit `2` with a usage error.
- `--offset <count>` — non-negative integer, default `0`. Number of
  ranked candidates to skip from the front of the ranked list
  before returning. Negative values cause the wrapper to exit `2`.
- `--json` — emit the envelope as JSON (see below)
- `--work-items-path <path>` — override the default location
- `--project-root <path>` — override the project root used for
  cross-repo manifest resolution

## Output schema

Per livespec/SPECIFICATION/contracts.md §"Implementation-plugin
contract — the 10-skill surface" → next and v005 §"next" → "Output
schema":

```json
{
  "candidates": [
    {
      "action": "implement",
      "work_item_ref": "<id>",
      "urgency": "high" | "medium" | "low",
      "reason": "<one-line narration>",
      "priority": <int>,
      "origin": "gap-tied" | "freeform"
    }
  ],
  "pagination": {
    "offset": 0,
    "limit": 5,
    "total": 12,
    "has_more": true
  }
}
```

Empty `candidates[]` IS the no-work signal — the wrapper does NOT
degrade to any legacy single-object shape. When `offset >= total`,
the wrapper emits `candidates: []` with `has_more: false`.

The `priority` and `origin` fields are impl-beads-specific
extensions; the cross-plugin contract permits additional fields on
each candidate per the upstream §"Output schema".

## When to use

- User asks "what should I work on next?"
- livespec's resident Layer 3 loop driver (at
  `livespec/.claude/skills/loop/SKILL.md`) composes
  `/livespec:next` + `/livespec-impl-beads:next` outputs into
  per-iteration recommendations.

Per the v089 upstream recast (livespec/SPECIFICATION/spec.md
§"Three-layer orchestration architecture" → "Layer 3 — Cross-repo
orchestration (livespec-resident)"), this skill does NOT carry a
Layer 3 discoverability nudge — that contract applies only to
/livespec:next, which is colocated with the resident Layer 3
driver in livespec. impl-plugin repos do NOT carry their own
Layer 3 driver, so a nudge from this skill would have no in-repo
surface to point at. The wrapper at
`.claude-plugin/scripts/bin/next.py` remains a pure
thin-transport pass-through.

## What this skill does NOT do

- It does NOT mutate any state. Read-only by contract.
- It does NOT invoke an LLM. The ranking is deterministic per the
  algorithm documented in
  livespec-impl-beads/SPECIFICATION/contracts.md §"next".
