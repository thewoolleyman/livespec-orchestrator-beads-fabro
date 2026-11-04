#!/usr/bin/env python3
"""Shebang wrapper for the canonical incident authority process protocol."""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.incident_authority import main

raise SystemExit(main())
