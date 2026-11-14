"""Petri-era client-version checks shared by the factory-graph gate."""

from __future__ import annotations

import re
import subprocess

__all__: list[str] = [
    "client_version",
    "is_petri_era_version",
    "version_refusal",
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


def version_refusal(*, binary: str, version: str | None) -> str | None:
    """Why a resolved client may not validate the graphs, or `None` when it may."""
    if version is None:
        return f"Petri-era client control: {binary} did not report a parseable version"
    if not is_petri_era_version(version=version):
        return f"Petri-era client control: fabro {version} is older than required 0.396.0"
    return None
