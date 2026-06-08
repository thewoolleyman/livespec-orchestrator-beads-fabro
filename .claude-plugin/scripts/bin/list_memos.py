#!/usr/bin/env python3
"""Shebang wrapper for list-memos. No logic; see livespec_impl_beads.commands.list_memos."""

from _bootstrap import bootstrap

bootstrap()

from livespec_impl_beads.commands.list_memos import main

raise SystemExit(main())
