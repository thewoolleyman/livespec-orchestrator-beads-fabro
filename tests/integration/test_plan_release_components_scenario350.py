"""Integration coverage for the plan-record release-component scenario.

The archive gate is exercised through its production archive entry point against
the hermetic beads client and a forge seam.  The records are deliberately
rendered first and then given their ratified artifact-path evidence line: the
separate posting-primitive payload is outside this scenario's implementation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_HOST_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_build_identity import (
    BuildIdentity,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_record_render import (
    RecordAssertion,
    render_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CAPTURED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.commands._plan_proof_record import (
    PLAN_PROOF_RECORD_TITLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_forge import (
    governed_repository_argv,
)
from livespec_orchestrator_beads_fabro.commands.plan import (
    PlanArchiveRefusedError,
    archive_thread,
    create_thread,
    record_completeness_review_evidence,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_ASSERTION = "The artifact has been exercised."
_COMPONENT = "shared-credentials"
_GOVERNED = "example/governed"
_TAG = "shared-credentials-v0.2.0"
_SLUG = "release-components"


@dataclass(kw_only=True)
class _Forge:
    tags: frozenset[str]
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, env, stdin
        self.calls.append(tuple(argv))
        if argv == governed_repository_argv():
            return CommandResult(exit_code=0, stdout=_GOVERNED, stderr="")
        return CommandResult(exit_code=0, stdout="\n".join(sorted(self.tags)), stderr="")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="release-components",
        prefix="bd-ib",
        server_user="release-components",
        database="release-components",
        bd_path="bd",
        fake=True,
    )


def _client() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _write_config(*, repo: Path, components: object) -> None:
    payload = {
        "livespec-orchestrator-beads-fabro": {"dispatcher": {"release_components": components}}
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(payload), encoding="utf-8")


def _body(*, verdict: str, paths: str | None) -> str:
    body = render_proof_record(
        title=PLAN_PROOF_RECORD_TITLE,
        verdict=verdict,
        identity=f"session {verdict}",
        timestamp="2026-11-11T00:00:00Z",
        build=BuildIdentity(release_tag=None, installed_build=None, commit="c0ffee1"),
        assertions=(
            RecordAssertion(
                text=_ASSERTION,
                proof_mode=PROOF_MODE_HOST_CAPTURED,
                governing_scenario=None,
                steps=("Run the artifact.",),
                proof="ok",
                reproduced=None if verdict == VERDICT_CAPTURED else True,
            ),
        ),
    )
    if paths is None:
        return body
    return body.replace("- Commit: c0ffee1", f"- Commit: c0ffee1\n- Artifact paths: {paths}")


def _archive(
    *, tmp_path: Path, components: object, tags: frozenset[str], paths: str | None
) -> None:
    reset_fake_singleton()
    repo = tmp_path / "governed"
    repo.mkdir()
    _write_config(repo=repo, components=components)
    created = create_thread(
        project_root=repo,
        config=_config(),
        slug=_SLUG,
        title="release components",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-11-11T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(statement="done", assertions=(_ASSERTION,)),
    )
    epic_id = created["epic_id"]
    record_completeness_review_evidence(
        config=_config(),
        epic_id=epic_id,
        evidence_id="review",
        env={"CLAUDE_CODE_SESSION_ID": "review"},
        reviewed_child_ids=(),
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="complete",
        now="2026-11-11T00:01:00Z",
    )
    for verdict in (VERDICT_CAPTURED, VERDICT_VERIFIED):
        _client().add_comment(issue_id=epic_id, body=_body(verdict=verdict, paths=paths))
    _ = archive_thread(
        project_root=repo,
        config=_config(),
        slug=_SLUG,
        epic_id=epic_id,
        completeness_review_comment_id="review",
        env={"CLAUDE_CODE_SESSION_ID": "archive"},
        runner=_Forge(tags=tags),
    )


def _components() -> list[dict[str, object]]:
    return [
        {
            "name": _COMPONENT,
            "tag_prefix": "shared-credentials-v",
            "paths": ["tools/shared_credentials/"],
        }
    ]


def test_an_artifact_outside_released_components_accepts_release_none(tmp_path: Path) -> None:
    _archive(
        tmp_path=tmp_path,
        components=_components(),
        tags=frozenset({_TAG}),
        paths="tools/shared_credentials_provisioning/",
    )


def test_an_artifact_under_a_released_component_refuses_release_none(tmp_path: Path) -> None:
    with pytest.raises(PlanArchiveRefusedError, match=_COMPONENT):
        _archive(
            tmp_path=tmp_path,
            components=_components(),
            tags=frozenset({_TAG}),
            paths="tools/shared_credentials/seal.py",
        )


def test_an_unowned_tag_keeps_the_repository_wide_rule(tmp_path: Path) -> None:
    with pytest.raises(PlanArchiveRefusedError, match=_GOVERNED):
        _archive(
            tmp_path=tmp_path,
            components=_components(),
            tags=frozenset({_TAG, "state-backend-v0.1.0"}),
            paths="tools/shared_credentials_provisioning/",
        )


def test_no_artifact_paths_keeps_the_repository_wide_rule(tmp_path: Path) -> None:
    with pytest.raises(PlanArchiveRefusedError, match=_GOVERNED):
        _archive(tmp_path=tmp_path, components=_components(), tags=frozenset({_TAG}), paths=None)


def test_a_malformed_component_declaration_rejects_every_record(tmp_path: Path) -> None:
    with pytest.raises(PlanArchiveRefusedError, match="dispatcher.release_components"):
        _archive(
            tmp_path=tmp_path,
            components=[{"name": _COMPONENT, "tag_prefix": "shared-credentials-v", "paths": []}],
            tags=frozenset({_TAG}),
            paths="tools/shared_credentials_provisioning/",
        )
