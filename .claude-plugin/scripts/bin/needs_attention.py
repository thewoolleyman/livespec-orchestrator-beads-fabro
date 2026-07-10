#!/usr/bin/env python3
"""Shebang wrapper for needs-attention. No logic; see livespec_orchestrator_beads_fabro.commands.needs_attention."""

from _bootstrap import bootstrap

__all__: list[str] = []

bootstrap()

from livespec_orchestrator_beads_fabro.commands.needs_attention import main

raise SystemExit(main())
