"""The dispatch-time Definition-of-Done wall resolves References against `origin/master`.

Measured 2026-11-09 on livespec-driver-codex-toclbe: the wall refused a
`## Scenario: ...` reference that had existed on the target repository's
`origin/master` for twelve minutes, because the primary checkout the wall read
still sat three commits behind. Auto-pulled primaries lag after any merge burst,
so these tests build the same shape for real: an origin that is AHEAD of a
clone, with the clone's working tree and its remote-tracking ref both stale.

Each test builds actual git repositories (a bare origin, a seed clone that
publishes revisions to it, and the primary checkout under test) rather than
stubbing the reader, because the behavior under test is exactly which revision
of the spec tree the wall consults.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    acceptance_eligibility,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_findings import (
    definition_of_done_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_filing_display import (
    MECHANICAL_FINDING_PREFIX,
    filing_display,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading_judge import (
    unjudged_governing_heading,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_OLD_HEADING = "## Scenario 1 — The heading the primary checkout already carries"
_NEW_HEADING = "## Scenario 2 — The heading only the remote carries"
_MISSING_HEADING = "## Scenario 999 — A heading no revision carries"
_GIT = (
    "git",
    "-c",
    "user.name=t",
    "-c",
    "user.email=t@example.invalid",
    "-c",
    "commit.gpgsign=false",
)


def _clean_environment() -> dict[str, str]:
    """The child environment without any GIT_ variable.

    This suite can itself run under a commit hook, whose `GIT_INDEX_FILE` would
    otherwise point the fixture's commits at the outer repository.
    """
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    return environment


def _run(*args: str, cwd: Path) -> None:
    _ = subprocess.run(
        [*_GIT, *args], cwd=cwd, check=True, capture_output=True, env=_clean_environment()
    )


def _publish(*, seed: Path, headings: tuple[str, ...], branch: str = "master") -> None:
    spec = seed / "SPECIFICATION"
    spec.mkdir(exist_ok=True)
    body = "# Scenarios\n\n" + "".join(f"{heading}\n\nProse.\n\n" for heading in headings)
    _ = (spec / "scenarios.md").write_text(body, encoding="utf-8")
    _run("add", "-A", cwd=seed)
    _run("commit", "-m", "revise", cwd=seed)
    _run("push", "origin", f"HEAD:refs/heads/{branch}", cwd=seed)


def _lagging_primary(*, tmp_path: Path, branch: str = "master") -> Path:
    """A primary checkout one revise behind its origin, the way a merge burst leaves it."""
    origin = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    primary = tmp_path / "primary"
    _run("init", "--bare", "-b", branch, str(origin), cwd=tmp_path)
    _run("init", "-b", branch, str(seed), cwd=tmp_path)
    _run("remote", "add", "origin", str(origin), cwd=seed)
    _publish(seed=seed, headings=(_OLD_HEADING,), branch=branch)
    _run("clone", str(origin), str(primary), cwd=tmp_path)
    _publish(seed=seed, headings=(_OLD_HEADING, _NEW_HEADING), branch=branch)
    return primary


def _item(*, references: str) -> WorkItem:
    description = (
        "## Definition of Done\n"
        "\n"
        "- The wall names the offending element of the section.\n"
        "\n"
        f"References: {references}\n"
    )
    return WorkItem(
        id="bd-ib-origin",
        type="bug",
        status="ready",
        title="A gated bug",
        description=description,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-09T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def test_a_heading_only_origin_master_carries_is_admitted(tmp_path: Path) -> None:
    primary = _lagging_primary(tmp_path=tmp_path)
    assert _NEW_HEADING not in (primary / "SPECIFICATION" / "scenarios.md").read_text(
        encoding="utf-8"
    )

    findings = definition_of_done_findings(item=_item(references=_NEW_HEADING), cwd=primary)

    assert findings == ()


def test_a_heading_neither_origin_master_nor_the_primary_carries_is_refused_by_name(
    tmp_path: Path,
) -> None:
    primary = _lagging_primary(tmp_path=tmp_path)

    refusal = acceptance_eligibility(item=_item(references=_MISSING_HEADING), cwd=primary).refusal

    assert refusal is not None
    assert _MISSING_HEADING in refusal


def test_a_heading_the_primary_alone_carries_is_refused(tmp_path: Path) -> None:
    # The primary is never the authority: a heading present only in a stale or
    # locally edited working tree is not on the remote and so is not resolved.
    primary = _lagging_primary(tmp_path=tmp_path)
    local_only = "## Scenario 3 — Only in the working tree"
    _ = (primary / "SPECIFICATION" / "scenarios.md").write_text(
        f"# Scenarios\n\n{local_only}\n", encoding="utf-8"
    )

    findings = definition_of_done_findings(item=_item(references=local_only), cwd=primary)

    assert len(findings) == 1
    assert local_only in findings[0]


def test_the_filing_display_and_the_wall_resolve_against_the_same_revision(
    tmp_path: Path,
) -> None:
    primary = _lagging_primary(tmp_path=tmp_path)
    item = _item(references=_NEW_HEADING)

    shown = filing_display(item=item, cwd=primary, governing=unjudged_governing_heading)
    wall = acceptance_eligibility(item=item, cwd=primary)

    mechanical = [line for line in shown.splitlines() if line.startswith(MECHANICAL_FINDING_PREFIX)]
    assert mechanical == []
    assert wall.findings == ()


def test_filing_against_a_configured_main_default_has_no_master_unreadable_finding(
    tmp_path: Path,
) -> None:
    primary = _lagging_primary(tmp_path=tmp_path, branch="main")
    _ = (primary / ".livespec.jsonc").write_text('{"canonical_branch": "main"}\n', encoding="utf-8")
    item = _item(references=_NEW_HEADING)

    shown = filing_display(item=item, cwd=primary, governing=unjudged_governing_heading)
    wall = acceptance_eligibility(item=item, cwd=primary)

    mechanical = [line for line in shown.splitlines() if line.startswith(MECHANICAL_FINDING_PREFIX)]
    assert mechanical == []
    assert wall.findings == ()


def test_filing_without_a_canonical_branch_uses_origin_head_for_main(
    tmp_path: Path,
) -> None:
    primary = _lagging_primary(tmp_path=tmp_path, branch="main")
    item = _item(references=_NEW_HEADING)

    shown = filing_display(item=item, cwd=primary, governing=unjudged_governing_heading)
    wall = acceptance_eligibility(item=item, cwd=primary)

    mechanical = [line for line in shown.splitlines() if line.startswith(MECHANICAL_FINDING_PREFIX)]
    assert mechanical == []
    assert wall.findings == ()


def test_an_unreadable_configured_main_origin_names_the_resolved_revision(
    tmp_path: Path,
) -> None:
    primary = _lagging_primary(tmp_path=tmp_path, branch="main")
    _ = (primary / ".livespec.jsonc").write_text('{"canonical_branch": "main"}\n', encoding="utf-8")
    _run("remote", "set-url", "origin", str(tmp_path / "gone.git"), cwd=primary)

    findings = definition_of_done_findings(item=_item(references=_OLD_HEADING), cwd=primary)

    assert len(findings) == 1
    assert "origin/main" in findings[0]
    assert "origin/master" not in findings[0]


def test_an_unreadable_origin_refuses_and_names_the_remote_revision(tmp_path: Path) -> None:
    primary = _lagging_primary(tmp_path=tmp_path)
    _run("remote", "set-url", "origin", str(tmp_path / "gone.git"), cwd=primary)
    # The working tree DOES carry this heading; judging against it would admit.
    item = _item(references=_OLD_HEADING)

    findings = definition_of_done_findings(item=item, cwd=primary)

    assert len(findings) == 1
    assert "origin/master" in findings[0]
    assert "unreadable" in findings[0]
    assert "does not resolve" not in findings[0]
