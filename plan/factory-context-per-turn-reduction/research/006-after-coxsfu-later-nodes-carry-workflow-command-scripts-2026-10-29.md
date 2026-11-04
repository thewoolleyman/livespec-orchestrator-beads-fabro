# 006 - After the prepare-step fix, later nodes still exceed 120k because the workflow's own command scripts are echoed the same way

Written 2026-10-29 ~00:30Z by an unattended resume of the session driving this plan. It records the host capture
taken for `bd-ib-coxsfu` (prepare-step scripts out of the agent preamble), which failed that item's host-captured
assertion, and the measured cause of the residual. It changes no plan assertion and no carrier.

## 1. Source and instrument

- Run: petri `01M621TE1F440FND66W2JN84F4` (bd-ib-nvhqyq), succeeded in 114m57s. It was dispatched by plugin cache
  build `933fcc119052`, which is release `v0.253.2`. The sudo journal at 2026-10-28T19:51:43Z names that build's
  `drive.py`, and `git tag --contains 3790b0d9f` (the fix commit) lists `v0.253.2`.
- Export: `fabro dump 01M621TE1F44 --server https://gmktec-xubuntu.perch-rudd.ts.net:32276 -o <dir>` with the petri
  carrier client `carrier-petri-v0.382-adeefec4c`. 248 files.
- Instrument: the same as note 003. ACP `usage_update` events at `item.record.body.ev.custom.event.update`, keyed by
  `custom.node`, `custom.firing` and `custom.attempt`. `used` is one request's whole context. 184 updates across 10
  agent node sessions.
- Engine rendering: petri `crates/attractor/steps/src/fidelity.rs` at `b99987b`. In `compact` mode, every completed
  `command` stage is rendered as `- Script: <full script>` plus the last 25 output lines. In `summary:high` mode it
  renders the full script plus the last 50 output lines, and every completed agent stage's `Response:`.

## 2. First request of every agent node session

| Session (node, firing) | Fidelity | First `used` | Within 120,000? |
|---|---|---:|---|
| dod_gate, 48 | compact | 111,834 | yes |
| implement, 49 | compact | 115,506 | yes |
| implement, 53 | compact | 117,931 | yes |
| fix, 57 | summary:high | 118,289 | yes |
| proof_capture, 61 | summary:high | 135,489 | no |
| review, 62 | compact | 127,009 | no |
| proof_verify, 63 | compact | 128,374 | no |
| proof_capture, 68 | summary:high | 150,487 | no |
| review, 69 | compact | 138,440 | no |
| proof_verify, 70 | compact | 139,787 | no |

The `bd-ib-coxsfu` fix worked for what it targeted. The floor fell from about 338k (note 003) to about 112k. The 46
prepare-step scripts now total 19,774 characters, and their payloads (344,229 characters) are in each step's `env`,
which the preamble does not render. The item's host-captured assertion still fails, because six of ten sessions open
above 120,000.

## 3. Where the growth after `fix` comes from

I rebuilt, for each agent session, what the completed non-prepare stages contribute to its preamble. For a command
stage that is its script, taken from the run's `graph.fabro`, plus the output tail for its fidelity, taken from
`stages/<n>/output.log`. For a `summary:high` session it also includes each completed agent stage's response, capped
at 8 KiB. The context-key list is not included in the rebuild.

| Session | Increase over dod_gate (tokens) | Rebuilt workflow-stage characters | Characters per token |
|---|---:|---:|---:|
| review, 62 | +15,175 | 36,158 | 2.4 |
| proof_verify, 63 | +16,540 | 36,158 | 2.2 |
| proof_capture, 61 | +23,655 | 52,119 | 2.2 |
| review, 69 | +26,606 | 64,110 | 2.4 |
| proof_verify, 70 | +27,953 | 64,110 | 2.3 |
| proof_capture, 68 | +38,653 | 88,458 | 2.3 |

The ratio is close to constant, so the rebuilt text accounts for the growth. Node prompts differ in size, so the
match is approximate and should not be read as exact.

The largest contributors are inline scripts in the committed graph
`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`:

| Command stage | Script characters | Output tail characters (25 lines / 50 lines) |
|---|---:|---|
| publish_draft | 20,626 | 1,453 / 8,030 |
| pr_refresh | 17,921 | 2,273 / 4,366 |
| pr | 16,378 | 650 / 650 |
| pr_refresh_head | 3,373 | 2,294 / 2,733 |
| implement_hook_route | 3,227 | 182 / 182 |
| janitor | 403 | 7,521 / 9,503 |

This is the mechanism of note 003 with a different emitter. The Dispatcher's prepare steps were the first emitter.
The workflow's own command nodes are the second. Each node runs once and is then re-carried in full on every turn of
every later agent node.

## 4. Consequences

- The remaining floor of about 112k is mostly the governed repository's instruction file (about 54.6k tokens, note
  003 section 3), the harness base (about 23k) and the goal plus node prompt. The C3 instruction-file split, which is
  held for the maintainer, is the largest remaining lever on the floor.
- The growth after `fix` comes from the workflow's inline command scripts and the janitor output. Moving the
  `publish_draft`, `pr_refresh`, `pr` and `pr_refresh_head` bodies into sandbox helper files would remove about 58k
  characters, or about 25k tokens. The mechanism would be the one `bd-ib-coxsfu` used: payloads written by a prepare
  step through `env`, with the node script reduced to a short invocation. An explicit fidelity on the late agent
  nodes that omits command scripts is the alternative. A Petri engine change remains the upstream last resort.
- Neither change alone brings `proof_capture` firing 68 under 120,000. Removing the four scripts would take it to about
  125k. Together with the C3 split, every FIRST request measured here would fall under 100,000. That is not plan
  assertion 2, which bounds the median over all responses: `implement` and `fix` grow far past their first request
  as their transcripts build up (note 005), and neither change addresses that growth.

## 5. Not decided here

Whether `bd-ib-coxsfu` is reworked to cover the workflow scripts, or its host assertion is carried by a successor
item under C2 or C4, is for the attended plan session. The failed capture, with the numbers in section 2, is recorded
on `bd-ib-coxsfu` (comment at 2026-10-28T22:09:47Z) and in the plan handoff at 2026-10-28T22:12Z.
