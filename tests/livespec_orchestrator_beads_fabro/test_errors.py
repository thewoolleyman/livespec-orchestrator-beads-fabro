"""Tests for the EXPECTED-error exception classes.

Covers both the inherited JSONL-shaped errors (kept for the spec-reader
and the thin-transport store-missing fallback) AND the beads-substrate
`Beads*Error` family landed in Phase C.
"""

from pathlib import Path

from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    MalformedRecordLineError,
    SchemaViolationError,
    SpecVersionNotFoundError,
    StoreFileMissingError,
)


def test_store_file_missing_error_message_and_attrs() -> None:
    path = Path("/tmp/work-items.jsonl")
    err = StoreFileMissingError(path=path)
    assert err.path == path
    assert str(err) == f"JSONL store file not found: {path}"


def test_malformed_record_line_error_message_and_attrs() -> None:
    path = Path("/tmp/work-items.jsonl")
    err = MalformedRecordLineError(
        path=path, line_number=42, raw_line="not-json\n", detail="JSON parse error: foo"
    )
    assert err.path == path
    assert err.line_number == 42
    assert err.raw_line == "not-json\n"
    assert err.detail == "JSON parse error: foo"
    assert str(err) == f"Malformed JSONL record at {path}:42: JSON parse error: foo"


def test_schema_violation_error_message_and_attrs() -> None:
    path = Path("/tmp/work-items.jsonl")
    err = SchemaViolationError(path=path, line_number=7, detail="missing key")
    assert err.path == path
    assert err.line_number == 7
    assert err.detail == "missing key"
    assert str(err) == f"Schema violation at {path}:7: missing key"


def test_spec_version_not_found_error_message_and_attrs() -> None:
    spec_root = Path("/tmp/SPECIFICATION")
    err = SpecVersionNotFoundError(spec_root=spec_root, version=42)
    assert err.spec_root == spec_root
    assert err.version == 42
    assert str(err) == (
        f"Specification history version v042 not found under {spec_root / 'history'}"
    )


# -- beads-substrate expected-error family (Phase C) ---------------------


def test_beads_connection_error_message_and_attrs() -> None:
    err = BeadsConnectionError(detail="connection refused")
    assert err.detail == "connection refused"
    assert str(err) == "Could not connect to the beads tenant server: connection refused"


def test_beads_command_error_message_and_attrs() -> None:
    err = BeadsCommandError(command="bd list --json", exit_code=3, stderr="boom")
    assert err.command == "bd list --json"
    assert err.exit_code == 3
    assert err.stderr == "boom"
    assert str(err) == "beads command failed (exit 3): bd list --json\nboom"


def test_beads_tenant_missing_error_message_and_attrs() -> None:
    err = BeadsTenantMissingError(tenant="livespec-impl-beads")
    assert err.tenant == "livespec-impl-beads"
    assert str(err) == "beads tenant database not found: livespec-impl-beads"


def test_beads_mapping_error_message_and_attrs() -> None:
    err = BeadsMappingError(record_id="li-abc123", detail="missing origin label")
    assert err.record_id == "li-abc123"
    assert err.detail == "missing origin label"
    assert str(err) == "Could not map beads record li-abc123: missing origin label"
