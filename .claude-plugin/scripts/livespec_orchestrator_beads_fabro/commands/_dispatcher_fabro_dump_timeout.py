"""The shared measured bound for Dispatcher ``fabro dump`` exports."""

from __future__ import annotations

__all__: list[str] = ["FABRO_DUMP_TIMEOUT_SECONDS"]

# Petri exported a 4.5-hour run in 815 seconds on 2026-11-02. Scenario 247
# ratifies 900 seconds, providing a fixed bound every Dispatcher dump shares.
FABRO_DUMP_TIMEOUT_SECONDS = 900
