"""`reconcile-merged --repo` admission: the path wall ahead of every config read.

The measured defect these bind (work-item `bd-ib-emzxlx`): a `--repo` value that
was a repository NAME rather than a repository PATH resolved to a relative path
that does not exist, the configuration read landed on an EMPTY block, and the
valve reported `connection.prefix is required` for a repository whose committed
configuration declares it. The refusal was true and its cause was wrong.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_preflight import (
    repo_path_refusal,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main

# The phrase the refusal states the requirement in. Named once so a test asserts
# the same bytes the module renders rather than a paraphrase of them.
_PATH_REQUIREMENT = "requires a path to an existing repository directory"
# The file whose absence the second refusal must NAME, because naming it is the
# whole difference between this refusal and the wrong-cause one it replaces.
_LIVESPEC_CONFIG = ".livespec.jsonc"


def _reconcile_argv(*, repo: str) -> list[str]:
    """One reconcile-merged invocation naming a never-filed item.

    The item is deliberately unfiled: every refusal here must land BEFORE the
    tenant read, so an invocation that got past the wall would die on
    "work-item not found" instead and the assertions would say so.
    """
    return ["reconcile-merged", "--repo", repo, "--item", "bd-ib-unfiled"]


@pytest.mark.parametrize("shape", ["absent-relative-name", "regular-file"])
def test_reconcile_merged_refuses_a_repo_value_that_is_not_an_existing_directory(
    shape: str,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both shapes are refused naming the submitted value and the requirement.

    `absent-relative-name` is the incident's own argument — the repository's
    NAME where its path belongs — and `regular-file` is the shape an existence
    test cannot tell from a repository: it exists, so the pre-fix valve read a
    configuration from it and then refused on the wrong cause.
    """
    monkeypatch.chdir(tmp_path)
    given = _non_directory_repo_value(shape=shape, tmp_path=tmp_path)

    exit_code = main(argv=_reconcile_argv(repo=given))

    err = capsys.readouterr().err
    assert given in err
    assert _PATH_REQUIREMENT in err
    assert exit_code == 3


def test_reconcile_merged_refuses_a_repo_directory_holding_no_livespec_config(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A directory with no `.livespec.jsonc` is refused with that file NAMED.

    Asserted at BOTH surfaces, and in this order on purpose. The wall itself is
    asserted first because it is what can refuse at all: before the fix this
    directory reached the configuration read, which raised rather than returning,
    so a CLI-only assertion would report a blown-up call instead of the missing
    refusal. The CLI invocation then proves the refusal reaches stderr at the
    precondition exit code rather than stopping at the wall's return value.
    """
    monkeypatch.chdir(tmp_path)
    repo = tmp_path / "repo-without-config"
    repo.mkdir()

    refusal = repo_path_refusal(repo=repo, given=str(repo))

    assert refusal is not None
    assert _LIVESPEC_CONFIG in refusal

    exit_code = main(argv=_reconcile_argv(repo=str(repo)))

    err = capsys.readouterr().err
    assert _LIVESPEC_CONFIG in err
    assert "connection.prefix" not in err
    assert exit_code == 3


def _non_directory_repo_value(*, shape: str, tmp_path: Path) -> str:
    if shape == "absent-relative-name":
        return "livespec-orchestrator-beads-fabro"
    regular_file = tmp_path / "livespec-orchestrator-beads-fabro"
    _ = regular_file.write_text("", encoding="utf-8")
    return str(regular_file)
