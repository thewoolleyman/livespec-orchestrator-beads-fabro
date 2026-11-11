"""Petri-era client-version checks shared by the factory-graph gate."""

from __future__ import annotations

import re
import subprocess

__all__: list[str] = [
    "client_version",
    "is_petri_era_version",
]


def client_version(*, binary: str) -> str | None:
    """Return the semantic version reported by a client, if it identifies itself."""
    completed = subprocess.run([binary, "--version"], capture_output=True, text=True, check=False)
    match = re.search(
        r"\bfabro (?P<version>\d+\.\d+\.\d+(?:-[^\s]+)?)",
        completed.stdout + completed.stderr,
    )
    return match.group("version") if match is not None else None


def is_petri_era_version(*, version: str) -> bool:
    """Whether version reaches the first upstream release with the Petri validator."""
    release = version.split("-", maxsplit=1)[0]
    return tuple(int(part) for part in release.split(".")) >= (0, 396, 0)
