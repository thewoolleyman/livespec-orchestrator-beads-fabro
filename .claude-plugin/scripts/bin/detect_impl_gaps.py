#!/usr/bin/env python3
"""Shebang wrapper for detect-impl-gaps. No logic; see livespec_orchestrator_beads_fabro.commands.detect_impl_gaps."""

from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.detect_impl_gaps import main

raise SystemExit(main())
