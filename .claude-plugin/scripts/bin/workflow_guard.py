#!/usr/bin/env python3
"""Shebang wrapper for workflow_guard. No logic; see livespec_orchestrator_beads_fabro.commands.workflow_guard."""

from _bootstrap import bootstrap

bootstrap(required=())

from livespec_orchestrator_beads_fabro.commands.workflow_guard import main

raise SystemExit(main())
