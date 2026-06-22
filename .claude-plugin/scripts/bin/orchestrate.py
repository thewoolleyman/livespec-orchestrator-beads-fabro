#!/usr/bin/env python3
"""Shebang wrapper for orchestrate. No logic; see livespec_orchestrator_beads_fabro.commands.orchestrate."""

from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.orchestrate import main

raise SystemExit(main())
