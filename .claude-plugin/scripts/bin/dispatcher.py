#!/usr/bin/env python3
"""Shebang wrapper for dispatcher. No logic; see livespec_impl_beads.commands.dispatcher."""

from _bootstrap import bootstrap

bootstrap()

from livespec_impl_beads.commands.dispatcher import main

raise SystemExit(main())
