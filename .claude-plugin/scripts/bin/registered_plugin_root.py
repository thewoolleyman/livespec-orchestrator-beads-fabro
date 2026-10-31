#!/usr/bin/env python3
"""Shebang wrapper for registered-plugin-root."""

from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.registered_plugin_root import main

raise SystemExit(main())
