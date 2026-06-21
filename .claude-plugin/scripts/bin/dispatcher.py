#!/usr/bin/env python3
"""Shebang wrapper for dispatcher. No logic; see livespec_orchestrator_beads_fabro.commands.dispatcher."""

from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.dispatcher import main

raise SystemExit(main())
