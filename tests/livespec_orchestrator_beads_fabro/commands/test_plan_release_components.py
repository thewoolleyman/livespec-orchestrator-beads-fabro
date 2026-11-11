"""The committed release-component declaration and artifact-path parser."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._plan_release_components import (
    artifact_paths_in,
    release_components,
)
from livespec_orchestrator_beads_fabro.commands._plan_release_repository import (
    InvalidReleaseComponents,
)

_REPOSITORY = "example/governed"


def _write_config(*, tmp_path: Path, components: object) -> None:
    payload = {
        "livespec-orchestrator-beads-fabro": {"dispatcher": {"release_components": components}}
    }
    _ = (tmp_path / ".livespec.jsonc").write_text(json.dumps(payload), encoding="utf-8")


def test_artifact_paths_are_read_from_the_first_case_insensitive_evidence_line() -> None:
    body = "\n".join(
        (
            "- Artifact Paths: tools/one/, , tools/two/",
            "- Artifact paths: tools/ignored/",
        )
    )

    assert artifact_paths_in(body=body) == ("tools/one/", "tools/two/")
    assert artifact_paths_in(body="no artifact declaration") == ()


@pytest.mark.parametrize(
    "components",
    [
        ({"name": "not-an-array"},),
        (["not-a-component"],),
        ([{"tag_prefix": "component-v", "paths": ["tools/component/"]}],),
        ([{"name": "", "tag_prefix": "component-v", "paths": ["tools/component/"]}],),
        ([{"name": "component", "paths": ["tools/component/"]}],),
        ([{"name": "component", "tag_prefix": "", "paths": ["tools/component/"]}],),
        ([{"name": "component", "tag_prefix": "component-v", "paths": []}],),
        ([{"name": "component", "tag_prefix": "component-v", "paths": "tools/component/"}],),
        ([{"name": "component", "tag_prefix": "component-v", "paths": [1]}],),
        ([{"name": "component", "tag_prefix": "component-v", "paths": [""]}],),
    ],
)
def test_malformed_component_declarations_are_configuration_findings(
    tmp_path: Path, components: object
) -> None:
    _write_config(tmp_path=tmp_path, components=components)

    result = release_components(project_root=tmp_path, repository=_REPOSITORY)

    assert isinstance(result, InvalidReleaseComponents)
    assert result.repository == _REPOSITORY
    assert "dispatcher.release_components" in result.finding


def test_an_absent_component_declaration_keeps_the_repository_wide_rule(tmp_path: Path) -> None:
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {}}}),
        encoding="utf-8",
    )

    assert release_components(project_root=tmp_path, repository=_REPOSITORY) is None


def test_a_valid_component_declaration_preserves_its_release_identity(tmp_path: Path) -> None:
    _write_config(
        tmp_path=tmp_path,
        components=[
            {
                "name": "component",
                "tag_prefix": "component-v",
                "paths": ["tools/component/"],
            }
        ],
    )

    result = release_components(project_root=tmp_path, repository=_REPOSITORY)

    assert result is not None
    assert not isinstance(result, InvalidReleaseComponents)
    assert result[0].name == "component"
    assert result[0].tag_prefix == "component-v"
    assert result[0].paths == ("tools/component/",)


def test_each_component_field_is_rejected_when_it_has_the_wrong_shape(tmp_path: Path) -> None:
    for components in (
        {"name": "not-an-array"},
        [{"name": "", "tag_prefix": "component-v", "paths": ["tools/component/"]}],
        [{"name": "component", "tag_prefix": "component-v", "paths": [""]}],
    ):
        _write_config(tmp_path=tmp_path, components=components)

        assert isinstance(
            release_components(project_root=tmp_path, repository=_REPOSITORY),
            InvalidReleaseComponents,
        )


@pytest.mark.parametrize(
    "path",
    ["/tools/component/", "../tools/component/", "tools/../../component/", "tools/..", ".."],
)
def test_a_component_path_that_is_not_repository_relative_is_a_configuration_finding(
    tmp_path: Path, path: str
) -> None:
    _write_config(
        tmp_path=tmp_path,
        components=[{"name": "component", "tag_prefix": "component-v", "paths": [path]}],
    )

    result = release_components(project_root=tmp_path, repository=_REPOSITORY)

    assert isinstance(result, InvalidReleaseComponents)
    assert "dispatcher.release_components" in result.finding
