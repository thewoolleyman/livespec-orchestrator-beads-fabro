#!/usr/bin/env python3
"""Shebang wrapper for list-plan-threads. No logic; see livespec_orchestrator_beads_fabro.commands.list_plan_threads."""

from _bootstrap import bootstrap

__all__: list[str] = []

bootstrap()

from livespec_orchestrator_beads_fabro.commands.list_plan_threads import main

raise SystemExit(main())
