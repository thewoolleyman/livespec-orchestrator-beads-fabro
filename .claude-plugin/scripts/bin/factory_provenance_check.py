#!/usr/bin/env python3
"""Shebang wrapper for factory-provenance-check. No logic; see livespec_orchestrator_beads_fabro.commands.factory_provenance_check."""

from _bootstrap import bootstrap

# This gate reads the Actions event payload and `git diff` ONLY — it never
# touches the beads tenant or the forge API, so it requires NO secret env and
# must NOT re-exec through the 1Password credential_wrapper (declare an empty
# `required` set). That is what "hermetic in the forge sense" buys: a merge
# gate that a tenant or credential outage cannot wedge.
bootstrap(required=())

from livespec_orchestrator_beads_fabro.commands.factory_provenance_check import main

raise SystemExit(main())
