"""Exception types for the expected-error surface of livespec-impl-beads.

Per SPECIFICATION/constraints.md §"Inherited from livespec" (the
Result-vs-bugs split), these are the EXPECTED errors the substrate or
external input can produce. Each carries enough context for the calling
skill to surface a clear narration to the user.

Unexpected errors (caller bugs, contract violations within the plugin's
own code) raise built-in exceptions (`ValueError`, `RuntimeError`, etc.)
and propagate to the outermost supervisor.

These classes are plain Exception subclasses (not @dataclass) because
dataclass-frozen with Exception inheritance hits CPython's __setattr__
discipline on self.args during super().__init__().
"""

from pathlib import Path


class StoreFileMissingError(Exception):
    """The configured JSONL store file did not exist on disk."""

    def __init__(self, *, path: Path) -> None:
        super().__init__(f"JSONL store file not found: {path}")
        self.path = path


class MalformedRecordLineError(Exception):
    """A line in the JSONL store could not be parsed as a JSON object."""

    def __init__(
        self,
        *,
        path: Path,
        line_number: int,
        raw_line: str,
        detail: str,
    ) -> None:
        super().__init__(f"Malformed JSONL record at {path}:{line_number}: {detail}")
        self.path = path
        self.line_number = line_number
        self.raw_line = raw_line
        self.detail = detail


class SchemaViolationError(Exception):
    """A parsed record's keys or values violated the schema contract."""

    def __init__(self, *, path: Path, line_number: int, detail: str) -> None:
        super().__init__(f"Schema violation at {path}:{line_number}: {detail}")
        self.path = path
        self.line_number = line_number
        self.detail = detail


class SpecVersionNotFoundError(Exception):
    """A requested vNNN/ directory did not exist under <spec-root>/history/."""

    def __init__(self, *, spec_root: Path, version: int) -> None:
        history_dir = spec_root / "history"
        super().__init__(
            f"Specification history version v{version:03d} not found under {history_dir}"
        )
        self.spec_root = spec_root
        self.version = version


class BeadsConnectionError(Exception):
    """The plugin could not reach the configured beads/Dolt tenant server."""

    def __init__(self, *, detail: str) -> None:
        super().__init__(f"Could not connect to the beads tenant server: {detail}")
        self.detail = detail


class BeadsCommandError(Exception):
    """An invoked `bd` CLI command exited non-zero or produced unparsable output."""

    def __init__(
        self,
        *,
        command: str,
        exit_code: int,
        stderr: str,
    ) -> None:
        super().__init__(
            f"beads command failed (exit {exit_code}): {command}\n{stderr}"
        )
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr


class BeadsTenantMissingError(Exception):
    """The configured per-repo tenant database was not present on the server."""

    def __init__(self, *, tenant: str) -> None:
        super().__init__(f"beads tenant database not found: {tenant}")
        self.tenant = tenant


class BeadsMappingError(Exception):
    """A beads record could not be mapped onto the work-item/memo schema."""

    def __init__(self, *, record_id: str, detail: str) -> None:
        super().__init__(f"Could not map beads record {record_id}: {detail}")
        self.record_id = record_id
        self.detail = detail
