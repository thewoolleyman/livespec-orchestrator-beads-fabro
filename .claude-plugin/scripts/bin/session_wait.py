#!/usr/bin/env python3
"""Shebang wrapper for session-wait. No logic; see livespec_orchestrator_beads_fabro.commands.session_wait."""

from _bootstrap import bootstrap

bootstrap(required=())

from livespec_orchestrator_beads_fabro.commands.session_wait import main

raise SystemExit(main())
