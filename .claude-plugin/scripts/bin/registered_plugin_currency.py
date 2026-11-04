#!/usr/bin/env python3
"""Shebang wrapper for registered-plugin-currency."""

from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.registered_plugin_currency import main

raise SystemExit(main())
