#!/usr/bin/env python3
"""Shebang wrapper for migrate-claim-tokens. No logic; see livespec_orchestrator_beads_fabro.commands.migrate_claim_tokens.

Private maintenance entry point for the sanctioned claim-token migration pass.
"""

from _bootstrap import bootstrap

bootstrap()

from livespec_orchestrator_beads_fabro.commands.migrate_claim_tokens import main

raise SystemExit(main())
