#!/usr/bin/env python3
"""Shebang wrapper for next. No logic; see livespec_orchestrator_beads_fabro.commands.next."""

from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.next import main

raise SystemExit(main())
