---
name: capture-memo
description: Low-friction free-text deposit of an in-flight observation. Memos are transient by construction and flow through `process-memos` for disposition. Required heavyweight authored skill per livespec/SPECIFICATION/contracts.md §"Heavyweight authored skills (6)". Invoke as `/livespec-impl-beads:capture-memo`.
allowed-tools: Bash, Write
---

# capture-memo

The deposit half of the memo lifecycle. Captures a single observation
the user is not yet ready to classify. Companion to `process-memos`,
which drains the queue.

## Pre-requisites

- The memos JSONL store path is reachable.
- `livespec_impl_beads` package on import path.

## Flow

### Step 1 — Ask for the memo text

> What's the observation?

Accept multi-line free-form text (markdown permitted). Do NOT ask for
classification, disposition, topic, work-item linkage, or any other
metadata — the entire point of this skill is low-friction deposit.
Classification happens in `process-memos`.

### Step 2 — Append

```python
from livespec_impl_beads._ids import new_memo_id
from livespec_impl_beads.commands._config import resolve_store_config
from livespec_impl_beads.store import append_memo
from livespec_impl_beads.types import Memo
from datetime import datetime, timezone
from pathlib import Path

config = resolve_store_config(cwd=Path.cwd(), work_items_arg=None, memos_arg=None)
memo = Memo(
    # A memo is a `kind:memo` issue in the SAME tenant, so its id carries
    # the configured tenant prefix (config.prefix), not a hardcoded `mm-`;
    # the `kind:memo` label is the discriminator.
    id=new_memo_id(prefix=config.prefix),
    text=text_from_user,
    state="untriaged",
    disposition=None,
    captured_at=datetime.now(tz=timezone.utc).isoformat(),
    work_item_id=None,
    knowledge_file=None,
    propose_change_topic=None,
)
append_memo(path=config, memo=memo)
```

Print the assigned id back. Do NOT ask "what disposition?" —
that's the next skill's job.

## Important properties

- **Transient by construction** — every memo MUST eventually flow
  through `process-memos` to one of the four canonical dispositions
  (spec-bound, impl-bound, persistent-knowledge, discard) per
  livespec/SPECIFICATION/spec.md §"Memo".
- **Low-friction** — no classification, no topic, no linkage at
  capture time. The whole skill is "ask for text, store it."
- **Doctor's memo-hygiene invariant** — when the untriaged queue grows
  beyond a configured threshold, doctor fires a `warn`. The remedy is
  to run `process-memos`, not to refuse new captures.

## What this skill does NOT do

- Does NOT classify memos. Use `process-memos`.
- Does NOT route to spec or impl side. The memo is a deposit; routing
  is `process-memos`'s job.
- Does NOT auto-link to work-items. The user can include such
  references in the memo `text` if they want, but no structured
  linkage is captured at this stage.
