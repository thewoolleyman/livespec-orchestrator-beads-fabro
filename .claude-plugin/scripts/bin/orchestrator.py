#!/usr/bin/env python3
"""Shebang wrapper for orchestrator. No logic; see livespec_impl_beads.commands.orchestrator."""

from _bootstrap import bootstrap

bootstrap()

from livespec_impl_beads.commands.orchestrator import main

raise SystemExit(main())
