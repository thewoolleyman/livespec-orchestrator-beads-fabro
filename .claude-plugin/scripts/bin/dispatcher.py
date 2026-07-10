#!/usr/bin/env python3
"""Shebang wrapper for dispatcher. No logic; see livespec_orchestrator_beads_fabro.commands.dispatcher."""

from _bootstrap import bootstrap

# The Dispatcher's factory GitHub auth resolves ONLY via the governed
# project's credential_wrapper into the App-token provider (github-app-auth
# Pillars 1+2), so the App env joins the tenant secret in the self-heal set.
bootstrap(required=("BEADS_DOLT_PASSWORD", "GITHUB_APP_ID", "GITHUB_PRIVATE_KEY"))

from livespec_orchestrator_beads_fabro.commands.dispatcher import main

raise SystemExit(main())
