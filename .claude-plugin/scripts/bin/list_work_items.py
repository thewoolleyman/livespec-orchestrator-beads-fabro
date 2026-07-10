#!/usr/bin/env python3
"""Shebang wrapper for list-work-items. No logic; see livespec_orchestrator_beads_fabro.commands.list_work_items."""

from _bootstrap import bootstrap

__all__: list[str] = []

bootstrap()

from livespec_orchestrator_beads_fabro.commands.list_work_items import main

raise SystemExit(main())
