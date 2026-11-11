"""The rendered run configuration carries the helper manifest and no helper source.

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch", paragraph
"Helper programs are fetched in the sandbox from the dispatching build's own
commit", and Scenario 336's "A dispatch's run configuration carries a helper
manifest and no helper source". Every emitter that used to carry a helper
program is switched on here, and the rendered overlay is graded: one fetch step
first among the Dispatcher's own, the manifest naming the installed build's
commit and one digest per helper, and no helper program's bytes anywhere.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands import _dispatcher_helper_build as build
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_projection import (
    CredentialUseProjection,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_registry import (
    helper_manifest,
    helper_registry,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import (
    render_run_config_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    PublicationMetadata,
)

from tests.prepare_step_support import readable

_COMMITTED = '[workflow]\ngraph = "workflow.fabro"\n[run.environment]\nid = "sandbox"\n'
_REPOSITORY = "https://github.com/thewoolleyman/livespec-orchestrator-beads-fabro.git"
_COMMIT = "0123456789abcdef0123456789abcdef01234567"
_MANIFEST_ENV = "LIVESPEC_DISPATCH_HELPER_MANIFEST"
# Opaque non-secret placeholders: the overlay renders whatever it is handed.
_TOKEN = "overlay-token-placeholder"
_GITHUB_TOKEN = "overlay-github-token-placeholder"
# Long enough that an accidental match is impossible, short enough to sit inside
# any one of the smallest helpers.
_PROBE_CHARS = 120


def _overlay(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str | None:
    monkeypatch.setenv("GITHUB_APP_ID", "1")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "key")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "2")
    return render_run_config_overlay(
        committed_text=_COMMITTED,
        workflow_dir=tmp_path,
        token=_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
        codex_auth_snapshot="{}",
        credential_use=CredentialUseProjection(
            deadline_epoch=1_799_999_999,
            credential_expiry_epoch=1_799_999_999,
            required_remaining_seconds=999,
        ),
        publication_metadata=PublicationMetadata(title="Title (bd-x)", body="Body of bd-x.\n"),
        dod_gate_subject="## Definition of Done\n\n- one.\n",
    )


@pytest.fixture(name="document")
def _document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    rendered = _overlay(tmp_path=tmp_path, monkeypatch=monkeypatch)
    assert rendered is not None
    return tomli.loads(rendered)


def test_the_first_dispatcher_step_fetches_the_installed_build_and_carries_the_manifest(
    document: dict[str, Any],
) -> None:
    steps = document["run"]["prepare"]["steps"]
    first = steps[0]
    assert "sparse-checkout set --no-cone" in first["script"]
    assert f"origin {_COMMIT}" in first["script"]
    manifest = json.loads(first["env"][_MANIFEST_ENV])
    assert manifest == helper_manifest(repository=_REPOSITORY, commit=_COMMIT)
    assert sum(_MANIFEST_ENV in step.get("env", {}) for step in steps) == 1


def test_no_helper_programs_bytes_ride_the_overlay(document: dict[str, Any]) -> None:
    steps = document["run"]["prepare"]["steps"]
    carried = [step["script"] for step in steps] + [
        readable(value=value)
        for step in steps
        for name, value in step.get("env", {}).items()
        if name != _MANIFEST_ENV
    ]
    carried += [str(value) for value in document["environments"]["sandbox"]["env"].values()]
    for helper in helper_registry():
        text = helper.compose().decode("utf-8")
        probe = text.strip()[:_PROBE_CHARS]
        if len(probe) < _PROBE_CHARS:
            continue
        assert not any(probe in value for value in carried), helper.name
    assert "LIVESPEC_CREDENTIAL_USE_GUARD_SCRIPT" not in document["environments"]["sandbox"]["env"]


def test_only_per_dispatch_data_rides_packed(document: dict[str, Any]) -> None:
    packed = [
        readable(value=value)
        for step in document["run"]["prepare"]["steps"]
        for name, value in step.get("env", {}).items()
        if name != _MANIFEST_ENV
    ]
    expected = {"## Definition of Done\n\n- one.\n", "Body of bd-x.\n"}
    # Compared by excerpt, so a failure names what rode packed without diffing it whole.
    unexpected = [value[:80] for value in packed if value not in expected]
    assert unexpected == []
    assert len(packed) == len(expected)


def test_a_build_with_no_identity_renders_no_overlay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_identity(**_kwargs: object) -> None:
        return None

    monkeypatch.setattr(build, "read_helper_source", no_identity)
    assert _overlay(tmp_path=tmp_path, monkeypatch=monkeypatch) is None


def test_a_passed_source_is_the_one_the_manifest_names(tmp_path: Path) -> None:
    source = build.HelperSource(repository="file:///forge/orchestrator", commit="f" * 40)
    rendered = render_run_config_overlay(
        committed_text=_COMMITTED,
        workflow_dir=tmp_path,
        token=_TOKEN,
        github_token=_GITHUB_TOKEN,
        siblings=None,
        helper_source=source,
    )
    assert rendered is not None
    first = tomli.loads(rendered)["run"]["prepare"]["steps"][0]
    assert json.loads(first["env"][_MANIFEST_ENV])["commit"] == "f" * 40
    assert "remote add origin file:///forge/orchestrator" in first["script"]
