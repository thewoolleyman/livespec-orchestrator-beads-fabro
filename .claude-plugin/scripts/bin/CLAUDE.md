# bin/

Shebang-wrapper executables (`#!/usr/bin/env python3`) — one per
thin-transport entry point (`detect_impl_gaps.py`,
`list_work_items.py`, `next.py`) plus `orchestrator.py`, the one
orchestrator-side contract CLI binary (subcommands `spec-reader`,
`gap-capture`, `drift-capture`; named in `.livespec.jsonc`'s
`orchestrator` section per livespec contracts.md §"Orchestrator CLI
contract — the three named CLIs"), plus `dispatcher.py`, the
orchestrator-PRIVATE Dispatcher CLI (subcommands `ledger-check`,
`dispatch`, `loop`; not contract surface, not config-named). Each
wrapper is a no-logic supervisor entry point of the canonical shape:

```
#!/usr/bin/env python3
"""Shebang wrapper for <cmd>. No logic; see livespec_impl_beads.commands.<cmd>."""

from _bootstrap import bootstrap

bootstrap()

from livespec_impl_beads.commands.<cmd> import main

raise SystemExit(main())
```

All logic lives in the imported `commands/<cmd>.py` module, per
`SPECIFICATION/constraints.md` §"Skill orchestration constraints"
("thin-transport skills carry ZERO orchestration ... All logic lives
in `.claude-plugin/scripts/bin/<skill>.py`" — realized as the wrapper
delegating to its `commands/` module).

`_bootstrap.py` is the one exception to the wrapper shape: it carries
the pre-package `sys.path` setup + Python version check, and is the
only file in this tree where `sys.stderr.write` is permitted before
structlog is configured.

`raise SystemExit(main())` is the permitted exit mechanism here. Do
NOT add argument parsing, business logic, or I/O to a wrapper — that
belongs in the `commands/` module so it stays under test coverage.
