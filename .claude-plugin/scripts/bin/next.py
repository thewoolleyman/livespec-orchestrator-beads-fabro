#!/usr/bin/env python3
"""Shebang wrapper for next. No logic; see livespec_impl_beads.commands.next."""

from _bootstrap import bootstrap

bootstrap()

from livespec_impl_beads.commands.next import main

raise SystemExit(main())
