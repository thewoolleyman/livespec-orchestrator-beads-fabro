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
from livespec_orchestrator_beads_fabro.errors import ConnectionPrefixMissingError

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


def test_the_connection_prefix_refusal_is_reached_only_for_a_config_that_was_read(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`connection.prefix` may only be blamed for a configuration actually READ.

    The two shapes are the discriminating pair. A `.livespec.jsonc` that is a
    DIRECTORY is PRESENT but is not a file the loader can read, so the loader
    falls back to an empty block and blames the prefix — the incident's own
    failure, reached through a path an existence test admits. A `.livespec.jsonc`
    that IS a readable file and declares no prefix is the one case the refusal
    describes truthfully, and it must keep firing.
    """
    monkeypatch.chdir(tmp_path)
    unreadable = tmp_path / "repo-with-unreadable-config"
    (unreadable / _LIVESPEC_CONFIG).mkdir(parents=True)
    prefixless = tmp_path / "repo-with-prefixless-config"
    prefixless.mkdir()
    _ = (prefixless / _LIVESPEC_CONFIG).write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"tenant": "t"}}}',
        encoding="utf-8",
    )

    unreadable_outcome, unreadable_err = _outcome(repo=unreadable, capsys=capsys)
    prefixless_outcome, _ = _outcome(repo=prefixless, capsys=capsys)

    assert unreadable_outcome == 3
    assert _LIVESPEC_CONFIG in unreadable_err
    assert isinstance(prefixless_outcome, ConnectionPrefixMissingError)


def _outcome(*, repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[object, str]:
    """One invocation's observable outcome: its exit code, or the raise.

    `ConnectionPrefixMissingError` is CAUGHT and RETURNED rather than allowed to
    escape, because whether it is REACHED is exactly what this assertion is
    about: a shape that reaches it and a shape that refuses must be compared
    side by side, and an escaping exception would end the test at the first one.
    """
    try:
        outcome: object = main(argv=_reconcile_argv(repo=str(repo)))
    except ConnectionPrefixMissingError as error:
        outcome = error
    return outcome, capsys.readouterr().err


def _non_directory_repo_value(*, shape: str, tmp_path: Path) -> str:
    if shape == "absent-relative-name":
        return "livespec-orchestrator-beads-fabro"
    regular_file = tmp_path / "livespec-orchestrator-beads-fabro"
    _ = regular_file.write_text("", encoding="utf-8")
    return str(regular_file)
