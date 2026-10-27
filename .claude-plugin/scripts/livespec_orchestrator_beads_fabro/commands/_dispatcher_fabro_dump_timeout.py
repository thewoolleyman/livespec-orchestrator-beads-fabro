"""The measured deadline every Dispatcher Fabro dump shares."""

from __future__ import annotations

__all__: list[str] = ["FABRO_DUMP_TIMEOUT_SECONDS"]

# Petri's longest measured dump took 465 seconds.  This fixed bound keeps
# roughly twice that duration while every Dispatcher reader uses one policy.
FABRO_DUMP_TIMEOUT_SECONDS = 900
