"""Shared plumbing for the `orchestrator` contract CLI subcommands.

Carries the orchestrator-CLI-private expected-error types plus the
three helpers every capture subcommand composes:

- `parse_cli_argv` — parse an injected-CLI flag value (a JSON array of
  strings, the argv-form convention of livespec's `.livespec.jsonc`
  config naming) into an argv list.
- `load_payload` — read a JSON payload from a file path or stdin
  (`-`), per the CLI shape convention "stdin/stdout plus files for
  payloads".
- `resolve_spec_version` — return the current spec version, through
  the INJECTED spec-reader CLI when one is supplied (the
  contract-level reference injection) or through the in-package Spec
  Reader otherwise (the same orchestrator owns both sides, so the
  internal API is a legitimate private interface).

The error types are defined here rather than `errors.py` because they
are private to the orchestrator CLI surface; nothing else in the
package raises or catches them.
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.spec_reader import current_specification_version

__all__: list[str] = [
    "CliContext",
    "InjectedCliError",
    "PayloadInvalidError",
    "PayloadMissingError",
    "as_non_empty_str_list",
    "load_payload",
    "parse_cli_argv",
    "require_str",
    "resolve_spec_version",
]


@dataclass(frozen=True, kw_only=True)
class CliContext:
    """The resolved addressing pair every subcommand operates against."""

    project_root: Path
    spec_root: Path


class PayloadMissingError(Exception):
    """The payload file named on the CLI did not exist on disk."""

    def __init__(self, *, path: Path) -> None:
        super().__init__(f"payload file not found: {path}")
        self.path = path


class PayloadInvalidError(Exception):
    """The inbound payload violated the JSON wire shape."""

    def __init__(self, *, detail: str) -> None:
        super().__init__(f"invalid payload: {detail}")
        self.detail = detail


class InjectedCliError(Exception):
    """An injected reference CLI failed or produced unusable output."""

    def __init__(self, *, argv: list[str], detail: str) -> None:
        super().__init__(f"injected CLI {argv!r} failed: {detail}")
        self.argv = argv
        self.detail = detail


def parse_cli_argv(*, raw: str, flag: str) -> list[str] | None:
    """Parse `raw` as a JSON array of non-empty strings (an argv form).

    Returns the argv list, or None (after a stderr usage narration)
    when the value is not a JSON array of non-empty strings. The
    caller maps None to the usage-error exit code 2.
    """
    try:
        parsed: object = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    argv = as_non_empty_str_list(value=parsed)
    if argv is not None:
        return argv
    _ = write_stderr(
        text=f"ERROR: {flag} requires a JSON array of non-empty strings (got {raw!r}).\n",
    )
    return None


def as_non_empty_str_list(*, value: object) -> list[str] | None:
    """Narrow `value` to a non-empty list of non-empty strings, else None."""
    if not isinstance(value, list):
        return None
    entries = cast("list[object]", value)
    strings = [entry for entry in entries if isinstance(entry, str) and entry != ""]
    if len(strings) == 0 or len(strings) != len(entries):
        return None
    return strings


def load_payload(*, source: str) -> object:
    """Read a JSON payload from `source` (a file path, or `-` for stdin).

    Raises `PayloadMissingError` when the named file is absent and
    `PayloadInvalidError` when the bytes do not parse as JSON.
    """
    if source == "-":
        text = sys.stdin.read()
    else:
        path = Path(source)
        if not path.is_file():
            raise PayloadMissingError(path=path)
        text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise PayloadInvalidError(detail=f"payload is not valid JSON: {exc}") from exc


def require_str(*, obj: dict[str, Any], key: str, where: str) -> str:
    """Return `obj[key]` as a non-empty string or raise `PayloadInvalidError`."""
    value: object = obj.get(key)
    if not isinstance(value, str) or value == "":
        raise PayloadInvalidError(detail=f"{where}.{key} must be a non-empty string")
    return value


def resolve_spec_version(*, spec_reader_cli: list[str] | None, context: CliContext) -> int:
    """Return the current spec version via the injected or internal reader."""
    if spec_reader_cli is None:
        return current_specification_version(spec_root=context.spec_root)
    argv = [
        *spec_reader_cli,
        "--project-root",
        str(context.project_root),
        "--spec-target",
        str(context.spec_root),
        "--json",
    ]
    completed = subprocess.run(  # noqa: S603 — fixed flag set over a caller-injected argv.
        argv,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise InjectedCliError(
            argv=spec_reader_cli,
            detail=f"exit {completed.returncode}: {completed.stderr.strip()}",
        )
    return _version_from_stdout(spec_reader_cli=spec_reader_cli, stdout=completed.stdout)


def _version_from_stdout(*, spec_reader_cli: list[str], stdout: str) -> int:
    try:
        parsed: object = json.loads(stdout)
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict):
        raise InjectedCliError(
            argv=spec_reader_cli,
            detail="stdout is not a JSON object",
        )
    version: object = cast("dict[str, Any]", parsed).get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise InjectedCliError(
            argv=spec_reader_cli,
            detail="stdout JSON carries no integer `version` key",
        )
    return version
