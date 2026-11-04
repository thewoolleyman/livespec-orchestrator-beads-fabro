"""Which `fabro` engine binary this host has, across BOTH deploy environments.

Split out of `_config` for the same reason `_node_timeouts` is: the answer
here is a HOST PROBE -- it asks the filesystem and `PATH` where a binary
actually is -- rather than configuration parsing, and it is the one value in
that module no `.livespec.jsonc` key can supply. `_config.resolve_fabro_bin`
remains the config-reading seam that layers `LIVESPEC_FABRO_BIN` and the
`dispatcher.fabro_bin` key over what this module finds.

The default probes the absolute home path before a bare `PATH` lookup because
the two envs that run with no explicit `--fabro-bin` disagree: the fleet
credential wrapper sanitizes `PATH` (secure_path, no `~/.local/bin`) but
PRESERVES `HOME`, so on the host the absolute `$HOME/.fabro/bin/fabro`
resolves where a bare `fabro` lookup fails; the orchestrator container instead
carries `fabro` at `/usr/local/bin/fabro` ON `PATH` with no `~/.fabro`, which
the `shutil.which` fallback finds.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

__all__: list[str] = [
    "configured_fabro_bin",
    "default_fabro_bin",
]


def configured_fabro_bin(*, block: dict[str, Any]) -> str:
    """The dispatcher block's `fabro_bin` key when non-empty, else the probe."""
    configured = block.get("fabro_bin")
    if isinstance(configured, str) and configured != "":
        return configured
    return default_fabro_bin()


def default_fabro_bin() -> str:
    """The default `fabro` path, resolved AT CALL TIME across BOTH deploy envs.

    Two environments run the Dispatcher with no explicit `--fabro-bin`:

    - Host-under-wrapper: the fleet credential wrapper sanitizes `PATH`
      (secure_path, no `~/.local/bin`) but PRESERVES `HOME`, so the binary at
      `$HOME/.fabro/bin/fabro` resolves by absolute path where a bare `fabro`
      PATH lookup would fail.
    - Orchestrator container (dark factory): `fabro` lives at
      `/usr/local/bin/fabro` ON `PATH`, and `$HOME/.fabro/bin/fabro` is absent.

    So the default probes the absolute home path FIRST (fixes the host bug),
    then falls back to a `PATH` lookup (works in the container). When neither
    resolves it returns the concrete home-path string so the preflight error
    names a real, actionable target rather than a bare name. Computed at call
    time (not import time) so a test that monkeypatches `Path.home()` /
    `shutil.which` observes the redirected values.

    A home candidate that cannot be probed (`OSError`, e.g. EACCES under an
    unreadable `$HOME`, which `Path.is_file` does not swallow) degrades to the
    same fallbacks as a missing one instead of aborting the Dispatcher.
    """
    home_candidate = Path.home() / ".fabro" / "bin" / "fabro"
    try:
        usable = home_candidate.is_file() and os.access(home_candidate, os.X_OK)
    except OSError:
        usable = False
    if usable:
        return str(home_candidate)
    found = shutil.which("fabro")
    if found is not None:
        return found
    return str(home_candidate)
