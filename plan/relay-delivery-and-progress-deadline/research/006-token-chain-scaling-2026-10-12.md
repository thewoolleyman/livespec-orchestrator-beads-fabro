# Does the epoch-token chain scale with item size or item lifetime?

Written 2026-10-12 by the relay session (Claude Code, session
`relay-delivery-and-progress-deadline`), in answer to the maintainer's
concern about research note 005's direction: "how many tokens it is going to
burn and whether that will scale linearly as the size of a work item scales,
or for long-lived work items."

"Tokens" has two readings here, and both are answered:

- **Token records**: the single-use ledger records the chain creates, and the
  `bd` calls and storage they cost.
- **LLM tokens**: the context an agent spends reading the ledger.

## Short answer

Neither grows with the size of a work item or with how long it lives,
PROVIDED two design rules hold. Both rules were measured below.

1. **Every token carries the full current state, never a delta.** The full
   state is the epoch, required result, original deadline, budget consumed,
   last attempt, and a bounded ring of the most recent operation receipts.
   Only the latest closed token and the current open token are ever needed,
   so the predecessor is deleted after each transition.
2. **Tokens are created with `--no-history`.** Such records are kept out of
   Dolt commit history and out of `bd list` and `list-work-items`. Unlike
   `--ephemeral`, they are not eligible for TTL compaction or purge, so the
   current token cannot be garbage-collected.

## Measurement: 60 transitions on one chain

Method. The probe built one disposable chain under `with-livespec-env.sh`
through the public `/usr/local/bin/bd`. Each transition did four things:
- created the writer's candidate next token;
- closed the current token with the full-state payload;
- read the token back to confirm the win, since the exit code does not name
  the winner (research 005);
- deleted the predecessor of the latest closed token.

After each transition the probe timed a resume read: `bd show` of the latest
closed token and of the current token. Every record was deleted afterwards
(`bd show` exits non-zero for all). Probe SHA256 prefix `332e0fc24e9c8fce`.

| Quantity | First 10 transitions | Last 10 transitions |
| --- | --- | --- |
| Write time per transition | 3.81 s mean | 3.91 s mean |
| `bd` calls per transition | 3 or 4 (no delete on the first) | 4 |
| Resume read (two `bd show`) | 1.15 s mean | 1.13 s mean |
| Payload bytes | 300 | 474, flat once the 8-entry receipt ring filled |
| Live token records | at most 2 | at most 2 |

Reading. Write cost, read cost, payload size and live record count are all
constant in the number of transitions. Each `bd` call costs about one second
on this host, mostly process start and connection. The payload's fields have
fixed size and do not include the item's description, criteria or comments,
so a larger work item does not make a larger token.

The cost is about four `bd` calls (about 4 s) per authority transition, ADDED
to today's handoff write of one comment plus one metadata update. Deleting the
predecessor could be done lazily, during the next transition or by a
reconciler, which would take that call off the critical path. That is an
implementation choice, not something this note measured.

## Measurement: what agents can see

Method. The probe created one no-history token and one ordinary control
record, then queried three surfaces. Both records were deleted afterwards.
Probe SHA256 prefix `37538cf9c2328abb`.

| Surface | Ordinary control | No-history token (`bd-ib-wisp-…`) |
| --- | --- | --- |
| `bd list --status all --limit 0 --json` | listed | **absent** |
| plugin `list_work_items.py --json` | listed | **absent** |
| `bd search <title>` | found | found |

The control proves each list surface could return a hit. Tokens therefore
add no LLM context to `next`, `list-work-items`, child enumeration or the
`context` envelope, all of which read through `bd list` or explicit parent
edges. Tokens are never linked to the epic. An agent sees a token only if it
runs `bd show` on its id or a text search for it.

## Where linear growth already exists today

The design does not add this, but it is the real LLM-token cost of a
long-lived plan, and the maintainer asked about long-lived items. This
epic's handoff timeline is 31 comments and 101,774 characters, about 25,000
LLM tokens. The `context` envelope and resume read it all. It grows by one
comment per handoff, so it is linear in the plan's lifetime. The token chain
leaves it unchanged. If anything, the chain lets a resume read authority from
one constant-size payload rather than parsing history. Bounding the timeline
itself (summarization, or reading only from the newest handoff) is a
separate question and is recorded here only as an observation.

## Still open

- Payload capacity is not a constraint: `close_reason` is LONGTEXT at
  v1.2.2 (migration 0049).
- The bounded receipt ring means a retry of an operation older than the last
  eight transitions cannot recover its original event by receipt. Such a
  retry is necessarily against an old epoch and is refused as stale. Whether
  that satisfies "retried calls with the same operation identity MUST recover
  the original event" for very old retries is a specification question to
  settle at the propose-change step.
- Released proof from two separate hosts is still owed (research 005).
