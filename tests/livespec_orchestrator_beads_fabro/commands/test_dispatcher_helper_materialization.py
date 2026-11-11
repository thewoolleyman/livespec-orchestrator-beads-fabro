"""Sandbox materialization of the dispatch helper manifest."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_helper_manifest as subject
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandResult


class _Runner:
    def __init__(self, *, exit_code: int = 0) -> None:
        self.exit_code = exit_code

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        value = "https://example.invalid/plugin.git\n" if argv[1] == "remote" else "a" * 40 + "\n"
        return CommandResult(exit_code=self.exit_code, stdout=value, stderr="")


def test_materializer_writes_the_composed_bytes_and_declared_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manifest recreates every fixed helper without carrying source text."""
    monkeypatch.setenv("LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT", str(tmp_path))
    manifest = subject.helper_manifest(
        repository="https://example.invalid/plugin.git", commit="a" * 40
    )

    subject.materialize_helpers(manifest=manifest)

    assert len(manifest["helpers"]) > 10
    for helper in manifest["helpers"]:
        written = tmp_path / Path(helper["path"]).relative_to("plugins")
        assert hashlib.sha256(written.read_bytes()).hexdigest() == helper["sha256"]
        assert written.stat().st_mode & 0o777 == helper["mode"]


def test_materializer_refuses_a_digest_that_does_not_describe_the_composed_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A source mismatch names the helper before any agent stage can run."""
    manifest = subject.helper_manifest(
        repository="https://example.invalid/plugin.git", commit="a" * 40
    )
    manifest["helpers"][0]["sha256"] = "0" * 64
    monkeypatch.setenv(subject.HELPER_MANIFEST_ENV, json.dumps(manifest))

    error = subject.materialize_helpers_from_environment()

    assert error is not None
    assert subject.HELPER_DIGEST_MISMATCH_CAUSE in error
    assert manifest["helpers"][0]["path"] in error


def test_manifest_source_and_fetch_step_pin_the_same_forge_commit() -> None:
    """The host reads the running build identity and fetches only that revision."""
    source = subject.dispatch_helper_source(runner=_Runner())

    assert source is not None
    assert source == subject.HelperSource(
        repository="https://example.invalid/plugin.git", commit="a" * 40
    )
    assert subject.helper_source_is_reachable(source=source, runner=_Runner())
    assert not subject.helper_source_is_reachable(source=source, runner=_Runner(exit_code=1))
    assert subject.dispatch_helper_source(runner=_Runner(exit_code=1)) is None
    rendered = subject.helper_fetch_prepare_steps_block(source=source)
    assert "--depth=1 --filter=blob:none" in rendered
    assert source.commit in rendered
    assert "sparse-checkout" in rendered
    assert "env = { LIVESPEC_PREPARE_PAYLOAD" not in rendered


def test_environment_materializer_names_a_missing_manifest() -> None:
    """A missing manifest is a named setup refusal rather than an agent failure."""
    previous = os.environ.pop(subject.HELPER_MANIFEST_ENV, None)
    try:
        error = subject.materialize_helpers_from_environment()
    finally:
        if previous is not None:
            os.environ[subject.HELPER_MANIFEST_ENV] = previous

    assert error is not None
    assert subject.HELPER_DIGEST_MISMATCH_CAUSE in error
