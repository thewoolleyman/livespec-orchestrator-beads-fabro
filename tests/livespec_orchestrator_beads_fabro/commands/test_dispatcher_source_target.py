"""Petri launch target rendering for disposable Dispatcher source trees."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_source_target import (
    explicit_source_target_argv,
)


@pytest.mark.parametrize(
    ("fabro_version", "origin_url", "origin_ref", "resume_branch", "argv", "expected"),
    [
        (
            "fabro 0.393.0 (fixture)",
            "https://github.com/example/source.git",
            "origin/master",
            None,
            ["fabro", "run", "workflow", "--server", "https://petri"],
            [
                "fabro",
                "run",
                "workflow",
                "--target",
                "example/source@master",
                "--server",
                "https://petri",
            ],
        ),
        (
            "fabro 0.393.0 (fixture)",
            "git@github.com:example/source.git",
            "origin/master",
            "feat/bd-ib-zedjgq",
            ["fabro", "run", "workflow"],
            ["fabro", "run", "workflow", "--target", "example/source@feat/bd-ib-zedjgq"],
        ),
        (
            "fabro 0.254.0 (fixture)",
            "https://github.com/example/source.git",
            "origin/master",
            None,
            ["fabro", "run", "workflow"],
            ["fabro", "run", "workflow"],
        ),
        (
            "fabro 0.393.0 (fixture)",
            "https://git.example.test/example/source.git",
            "origin/master",
            None,
            ["fabro", "run", "workflow"],
            ["fabro", "run", "workflow"],
        ),
        (
            "fabro 0.393.0 (fixture)",
            "https://notgithub.com/example/source.git",
            "origin/master",
            None,
            ["fabro", "run", "workflow"],
            ["fabro", "run", "workflow"],
        ),
        (
            "fabro 0.393.0 (fixture)",
            "https://git.example.test/github.com/example/source.git",
            "origin/master",
            None,
            ["fabro", "run", "workflow"],
            ["fabro", "run", "workflow"],
        ),
        (
            "fabro 0.393.0 (fixture)",
            "https://x-access-token:secret@github.com/example/source.git",
            "origin/master",
            None,
            ["fabro", "run", "workflow"],
            ["fabro", "run", "workflow", "--target", "example/source@master"],
        ),
        (
            "fabro 0.393.0 (fixture)",
            "ssh://git@github.com/example/source.git",
            "origin/master",
            None,
            ["fabro", "run", "workflow"],
            ["fabro", "run", "workflow", "--target", "example/source@master"],
        ),
        (
            "fabro 0.393.0 (fixture)",
            "https://github.com/example",
            "origin/master",
            None,
            ["fabro", "run", "workflow"],
            ["fabro", "run", "workflow"],
        ),
        (
            "fabro 0.393.0 (fixture)",
            "https://github.com/example/.git",
            "origin/master",
            None,
            ["fabro", "run", "workflow"],
            ["fabro", "run", "workflow"],
        ),
    ],
)
def test_explicit_source_target_argv_preserves_only_supported_launches(
    *,
    fabro_version: str,
    origin_url: str,
    origin_ref: str,
    resume_branch: str | None,
    argv: list[str],
    expected: list[str],
) -> None:
    assert (
        explicit_source_target_argv(
            argv=argv,
            fabro_version=fabro_version,
            origin_url=origin_url,
            origin_ref=origin_ref,
            resume_branch=resume_branch,
        )
        == expected
    )
