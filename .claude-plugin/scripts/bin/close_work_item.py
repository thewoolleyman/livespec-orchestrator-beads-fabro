#!/usr/bin/env python3
"""Shebang wrapper for close-work-item. No logic; see livespec_orchestrator_beads_fabro.commands.close_work_item."""

from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.close_work_item import main

raise SystemExit(main())
