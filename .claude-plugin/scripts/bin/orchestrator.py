#!/usr/bin/env python3
"""Shebang wrapper for orchestrator. No logic; see livespec_orchestrator_beads_fabro.commands.orchestrator."""

from _bootstrap import bootstrap

__all__: list[str] = []

bootstrap()

from livespec_orchestrator_beads_fabro.commands.orchestrator import main

raise SystemExit(main())
