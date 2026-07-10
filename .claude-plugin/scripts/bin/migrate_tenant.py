#!/usr/bin/env python3
"""Shebang wrapper for migrate-tenant. No logic; see livespec_orchestrator_beads_fabro.commands.migrate_tenant.

Private maintenance entry point for tenant bootstrap.
"""

from _bootstrap import bootstrap

__all__: list[str] = []

bootstrap()

from livespec_orchestrator_beads_fabro.commands.migrate_tenant import main

raise SystemExit(main())
