#!/usr/bin/env python3
"""Shebang wrapper for mint-app-token. No logic; see livespec_orchestrator_beads_fabro.commands.mint_app_token."""

from _bootstrap import bootstrap

__all__: list[str] = []

# A GitHub App token mint needs the App env ALONE — never the Dolt tenant
# secret (the entrypoint's github provisioning runs in contexts that do not
# carry it). Self-heal still routes through the project's credential_wrapper.
bootstrap(required=("GITHUB_APP_ID", "GITHUB_PRIVATE_KEY"))

from livespec_orchestrator_beads_fabro.commands.mint_app_token import main

raise SystemExit(main())
