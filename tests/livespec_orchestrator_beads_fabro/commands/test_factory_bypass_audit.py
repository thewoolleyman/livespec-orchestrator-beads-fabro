"""Hermetic tests for the factory-bypass audit command.

No network: the `gh` transport is an injected `GhSeam` fake returning canned
`gh pr list --json ...` stdout, mirroring how sibling command modules fake
their side-effecting seams (e.g. `needs_attention`'s `SpecNextSeam`).
"""

from __future__ import annotations

import json

import pytest
from livespec_orchestrator_beads_fabro.commands.factory_bypass_audit import (
    AuditPolicy,
    BypassFinding,
    GhSeam,
    PullRequest,
    audit_pull_requests,
    fetch_merged_prs,
    is_product_py,
    main,
    parse_pr_list,
    render_json,
    render_report,
)

_FACTORY = "app/livespec-pr-bot"
_PRODUCT = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/foo.py"


def _policy(
    *,
    allow_authors: frozenset[str] = frozenset(),
    allow_labels: frozenset[str] = frozenset(),
) -> AuditPolicy:
    return AuditPolicy(
        factory_app_login=_FACTORY,
        allow_authors=allow_authors,
        allow_labels=allow_labels,
    )


def _pr(
    *,
    number: int = 1,
    author: str = "thewoolleyman",
    files: tuple[str, ...] = (_PRODUCT,),
    labels: tuple[str, ...] = (),
) -> PullRequest:
    return PullRequest(
        number=number,
        title="feat: change",
        author_login=author,
        files=files,
        labels=labels,
    )


def _seam(*, stdout: str, recorder: list[list[str]] | None = None) -> GhSeam:
    def _run(*, args: list[str]) -> str:
        if recorder is not None:
            recorder.append(args)
        return stdout

    return GhSeam(run=_run)


# --------------------------------------------------------------------------
# is_product_py — the classifier
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        _PRODUCT,
        ".claude-plugin/scripts/bin/factory_bypass_audit.py",
        "dev-tooling/checks/foo.py",
    ],
)
def test_is_product_py_true(path: str) -> None:
    assert is_product_py(path=path) is True


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/foo.txt",
        "tests/livespec_orchestrator_beads_fabro/commands/test_foo.py",
        ".claude-plugin/scripts/_vendor/structlog/foo.py",
        ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/__pycache__/foo.py",
        "plan/force-factory/findings.py",
    ],
)
def test_is_product_py_false(path: str) -> None:
    assert is_product_py(path=path) is False


# --------------------------------------------------------------------------
# audit_pull_requests — the flagging rule
# --------------------------------------------------------------------------


def test_flags_product_code_pr_by_non_app_author() -> None:
    report = audit_pull_requests(prs=[_pr(number=42)], policy=_policy())
    assert report.scanned == 1
    assert report.findings == (
        BypassFinding(
            number=42,
            title="feat: change",
            author_login="thewoolleyman",
            product_paths=(_PRODUCT,),
        ),
    )


def test_does_not_flag_factory_app_pr() -> None:
    report = audit_pull_requests(prs=[_pr(author=_FACTORY)], policy=_policy())
    assert report.findings == ()


def test_does_not_flag_allowlisted_author() -> None:
    report = audit_pull_requests(
        prs=[_pr(author="release-bot")],
        policy=_policy(allow_authors=frozenset({"release-bot"})),
    )
    assert report.findings == ()


def test_does_not_flag_allowlisted_label() -> None:
    report = audit_pull_requests(
        prs=[_pr(labels=("factory-bypass-approved",))],
        policy=_policy(allow_labels=frozenset({"factory-bypass-approved"})),
    )
    assert report.findings == ()


def test_does_not_flag_non_product_pr() -> None:
    report = audit_pull_requests(
        prs=[_pr(files=("README.md", "plan/x.md"))],
        policy=_policy(),
    )
    assert report.scanned == 1
    assert report.findings == ()


def test_only_product_paths_are_carried() -> None:
    report = audit_pull_requests(
        prs=[_pr(files=(_PRODUCT, "README.md"))],
        policy=_policy(),
    )
    assert report.findings[0].product_paths == (_PRODUCT,)


# --------------------------------------------------------------------------
# parse_pr_list — the gh JSON reduction
# --------------------------------------------------------------------------


def test_parse_pr_list_reduces_fields() -> None:
    stdout = json.dumps(
        [
            {
                "number": 100,
                "title": "feat: x",
                "author": {"login": "thewoolleyman"},
                "files": [{"path": _PRODUCT}, {"path": "README.md"}],
                "labels": [{"name": "enhancement"}],
            },
            {"number": 101, "author": None, "files": [], "labels": []},
        ]
    )
    prs = parse_pr_list(stdout=stdout)
    assert prs[0] == PullRequest(
        number=100,
        title="feat: x",
        author_login="thewoolleyman",
        files=(_PRODUCT, "README.md"),
        labels=("enhancement",),
    )
    # Missing author / title default to empty; a null author yields "".
    assert prs[1] == PullRequest(number=101, title="", author_login="", files=(), labels=())


# --------------------------------------------------------------------------
# fetch_merged_prs — argv construction over the seam
# --------------------------------------------------------------------------


def test_fetch_merged_prs_default_window() -> None:
    recorder: list[list[str]] = []
    prs = fetch_merged_prs(
        repo=None,
        limit=100,
        merged_since=None,
        seam=_seam(stdout="[]", recorder=recorder),
    )
    assert prs == []
    args = recorder[0]
    assert args[:6] == ["pr", "list", "--state", "merged", "--limit", "100"]
    assert "--repo" not in args
    assert "--search" not in args


def test_fetch_merged_prs_repo_and_since() -> None:
    recorder: list[list[str]] = []
    _ = fetch_merged_prs(
        repo="thewoolleyman/livespec-orchestrator-beads-fabro",
        limit=25,
        merged_since="2026-06-15",
        seam=_seam(stdout="[]", recorder=recorder),
    )
    args = recorder[0]
    assert "--repo" in args
    assert args[args.index("--repo") + 1] == "thewoolleyman/livespec-orchestrator-beads-fabro"
    assert args[args.index("--search") + 1] == "merged:>=2026-06-15"
    assert args[args.index("--limit") + 1] == "25"


# --------------------------------------------------------------------------
# render_report / render_json
# --------------------------------------------------------------------------


def test_render_report_no_findings() -> None:
    report = audit_pull_requests(prs=[_pr(author=_FACTORY)], policy=_policy())
    text = render_report(report=report, policy=_policy())
    assert "No factory bypasses found" in text
    assert "Scanned 1 recently-merged PR(s)." in text


def test_render_report_with_findings() -> None:
    report = audit_pull_requests(prs=[_pr(number=7)], policy=_policy())
    text = render_report(report=report, policy=_policy())
    assert "Flagged 1 product-code PR(s)" in text
    assert "- PR #7 by @thewoolleyman" in text
    assert f"    - {_PRODUCT}" in text


def test_render_json_shape() -> None:
    report = audit_pull_requests(prs=[_pr(number=7)], policy=_policy())
    payload = json.loads(render_json(report=report, policy=_policy()))
    assert payload["scanned"] == 1
    assert payload["count"] == 1
    assert payload["factory_app_login"] == _FACTORY
    assert payload["findings"][0]["number"] == 7
    assert payload["findings"][0]["product_paths"] == [_PRODUCT]


def test_render_json_empty() -> None:
    report = audit_pull_requests(prs=[], policy=_policy())
    payload = json.loads(render_json(report=report, policy=_policy()))
    assert payload["count"] == 0
    assert payload["findings"] == []


# --------------------------------------------------------------------------
# main — the CLI supervisor
# --------------------------------------------------------------------------


def _stdout_one_bypass() -> str:
    return json.dumps(
        [
            {
                "number": 55,
                "title": "feat: sneaky",
                "author": {"login": "thewoolleyman"},
                "files": [{"path": _PRODUCT}],
                "labels": [],
            }
        ]
    )


def test_main_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(argv=[], seam=_seam(stdout=_stdout_one_bypass()))
    assert code == 0
    out = capsys.readouterr().out
    assert "# Factory-Bypass Audit" in out
    assert "- PR #55 by @thewoolleyman" in out


def test_main_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(argv=["--json"], seam=_seam(stdout=_stdout_one_bypass()))
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1


def test_main_factory_login_override_flags_default_app(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Overriding the factory login unexempts the default App identity."""
    stdout = json.dumps(
        [
            {
                "number": 9,
                "title": "feat: y",
                "author": {"login": _FACTORY},
                "files": [{"path": _PRODUCT}],
                "labels": [],
            }
        ]
    )
    code = main(
        argv=["--json", "--factory-app-login", "someone-else"],
        seam=_seam(stdout=stdout),
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert payload["findings"][0]["author"] == _FACTORY


def test_main_allow_author_and_label(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        argv=["--json", "--allow-author", "thewoolleyman"],
        seam=_seam(stdout=_stdout_one_bypass()),
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["count"] == 0


def test_main_threads_limit_and_since_to_gh(capsys: pytest.CaptureFixture[str]) -> None:
    recorder: list[list[str]] = []
    code = main(
        argv=["--limit", "5", "--merged-since", "2026-07-01", "--repo", "o/r"],
        seam=_seam(stdout="[]", recorder=recorder),
    )
    assert code == 0
    args = recorder[0]
    assert args[args.index("--limit") + 1] == "5"
    assert args[args.index("--search") + 1] == "merged:>=2026-07-01"
    assert args[args.index("--repo") + 1] == "o/r"
    assert "No factory bypasses found" in capsys.readouterr().out
