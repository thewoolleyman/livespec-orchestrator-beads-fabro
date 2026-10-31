"""Render non-secret OpenTelemetry environment projection for a sandbox."""

from __future__ import annotations

import json

__all__: list[str] = ["otel_env_lines"]


def otel_env_lines(*, otel_env: dict[str, str] | None) -> str:
    """Render the in-sandbox CC OTel keys as environment-table lines.

    Absent OTel configuration retains the token-only overlay shape.  Sorting
    makes the result stable and JSON quoting keeps every value valid TOML.
    Values are non-secret receiver configuration; the Honeycomb ingest key is
    deliberately not projected into a sandbox.
    """
    if otel_env is None:
        return ""
    return "".join(f"{key} = {json.dumps(otel_env[key])}\n" for key in sorted(otel_env))
