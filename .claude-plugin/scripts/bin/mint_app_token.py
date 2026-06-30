#!/usr/bin/env python3
"""Shebang wrapper for mint-app-token. No logic; see livespec_orchestrator_beads_fabro.commands.mint_app_token."""

from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.mint_app_token import main

raise SystemExit(main())
