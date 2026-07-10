#!/usr/bin/env python3
"""Shebang wrapper for orchestrator. No logic; see livespec_orchestrator_beads_fabro.commands.orchestrator."""

from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.orchestrator import main

raise SystemExit(main())
