#!/usr/bin/env python3
"""Shebang wrapper for factory-bypass-audit. No logic; see livespec_orchestrator_beads_fabro.commands.factory_bypass_audit."""

from _bootstrap import bootstrap

# This audit reads GitHub via `gh` (its own auth) ONLY — it never touches the
# beads tenant, so it requires NO secret env and must NOT re-exec through the
# 1Password credential_wrapper (declare an empty `required` set).
bootstrap(required=())

from livespec_orchestrator_beads_fabro.commands.factory_bypass_audit import main

raise SystemExit(main())
