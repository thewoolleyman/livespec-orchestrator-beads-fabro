#!/usr/bin/env python3
"""Shebang wrapper for take-candidate-canary. No logic; see livespec_orchestrator_beads_fabro.commands.take_candidate_canary."""

from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.take_candidate_canary import main

raise SystemExit(main())
