#!/usr/bin/env python3
"""Shebang wrapper for drive. No logic; see livespec_orchestrator_beads_fabro.commands.drive."""

from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.drive import main

raise SystemExit(main())
