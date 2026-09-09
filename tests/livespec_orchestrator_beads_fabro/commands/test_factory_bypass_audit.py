"""Hermetic tests for the factory-bypass audit command.

No network: the `gh` transport is an injected `GhSeam` fake returning canned
`gh pr list --json ...` stdout, mirroring how sibling command modules fake
their side-effecting seams (e.g. `needs_attention`'s `SpecNextSeam`).

The seam now answers TWO reads — the merged-PR window and the audited
repository's `pyproject.toml` — so the fake dispatches on the first argv token
rather than returning one canned body for everything.
"""

from __future__ import annotations

import json

import pytest
from livespec_orchestrator_beads_fabro.commands._factory_bypass_gh import GhSeam, PullRequest
from livespec_orchestrator_beads_fabro.commands._factory_bypass_product_paths import (
    ProductPathPolicy,
    product_policy,
)
from livespec_orchestrator_beads_fabro.commands.factory_bypass_audit import (
    DEFAULT_FACTORY_APP_LOGIN,
    AuditPolicy,
    BypassFinding,
    RecordedException,
    audit_pull_requests,
    carries_factory_override,
    main,
    render_json,
    render_report,
    resolve_product_policy,
)

_FACTORY = "app/livespec-pr-bot"
_PRODUCT = ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/foo.py"
_DEV_TOOLING_PRODUCT = "livespec_dev_tooling/checks/red_green_replay.py"

_ORCHESTRATOR_PYPROJECT = (
    "[tool.livespec_dev_tooling]\n"
    'source_tree_prefixes = [".claude-plugin/scripts/livespec_orchestrator_beads_fabro/",'
    ' ".claude-plugin/scripts/bin/"]\n'
)
_DEV_TOOLING_PYPROJECT = (
    '[tool.livespec_dev_tooling]\nsource_tree_prefixes = ["livespec_dev_tooling/"]\n'
)


def _product_paths(*, pyproject_text: str = _ORCHESTRATOR_PYPROJECT) -> ProductPathPolicy:
    return product_policy(pyproject_text=pyproject_text)


def _policy(
    *,
    allow_authors: frozenset[str] = frozenset(),
    allow_labels: frozenset[str] = frozenset(),
    product_paths: ProductPathPolicy | None = None,
) -> AuditPolicy:
    return AuditPolicy(
        factory_app_login=_FACTORY,
        allow_authors=allow_authors,
        allow_labels=allow_labels,
        product_paths=_product_paths() if product_paths is None else product_paths,
    )


def _pr(
    *,
    number: int = 1,
    author: str = "thewoolleyman",
    files: tuple[str, ...] = (_PRODUCT,),
    labels: tuple[str, ...] = (),
    commit_messages: tuple[str, ...] = (),
) -> PullRequest:
    return PullRequest(
        number=number,
        title="feat: change",
        author_login=author,
        files=files,
        labels=labels,
        commit_messages=commit_messages,
    )


def _seam(
    *,
    prs_stdout: str,
    pyproject: str = _ORCHESTRATOR_PYPROJECT,
    recorder: list[list[str]] | None = None,
) -> GhSeam:
    """Fake `gh`: dispatches on the verb so both audit reads are answerable."""

    def _run(*, args: list[str]) -> str:
        if recorder is not None:
            recorder.append(args)
        return pyproject if args[0] == "api" else prs_stdout

    return GhSeam(run=_run)


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
    assert report.exceptions == ()


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


def test_audits_another_repo_layout_under_that_repos_policy() -> None:
    """The fleet-blindness regression: dev-tooling product code must classify."""
    prs = [_pr(number=8, files=(_DEV_TOOLING_PRODUCT,))]
    blind = audit_pull_requests(prs=prs, policy=_policy())
    seeing = audit_pull_requests(
        prs=prs,
        policy=_policy(product_paths=_product_paths(pyproject_text=_DEV_TOOLING_PYPROJECT)),
    )
    assert blind.findings == ()
    assert seeing.findings[0].number == 8


# --------------------------------------------------------------------------
# Factory-Override — a declared bypass is a recorded exception
# --------------------------------------------------------------------------


def test_carries_factory_override_detects_the_trailer_line() -> None:
    assert carries_factory_override(
        pr=_pr(commit_messages=("feat: x\nFactory-Override: red master",))
    )
    assert carries_factory_override(pr=_pr(commit_messages=("feat: x\nno trailer here",))) is False
    assert carries_factory_override(pr=_pr()) is False


def test_factory_override_pr_is_a_recorded_exception_not_a_bypass() -> None:
    report = audit_pull_requests(
        prs=[_pr(number=13, commit_messages=("fix: y\n\nFactory-Override: master red",))],
        policy=_policy(),
    )
    assert report.findings == ()
    assert report.exceptions == (
        RecordedException(number=13, title="feat: change", author_login="thewoolleyman"),
    )


# --------------------------------------------------------------------------
# resolve_product_policy — per-repository resolution through the seam
# --------------------------------------------------------------------------


def test_resolve_product_policy_derives_from_the_audited_repo() -> None:
    policy = resolve_product_policy(
        repo="thewoolleyman/livespec-dev-tooling",
        seam=_seam(prs_stdout="[]", pyproject=_DEV_TOOLING_PYPROJECT),
    )
    assert policy.origin == "declared"
    assert policy.prefixes == ("livespec_dev_tooling/",)


def test_resolve_product_policy_prefers_an_operator_override() -> None:
    policy = resolve_product_policy(
        repo=None,
        overrides=("src/",),
        seam=_seam(prs_stdout="[]"),
    )
    assert policy.origin == "operator-override"
    assert policy.prefixes == ("src/",)


# --------------------------------------------------------------------------
# render_report / render_json
# --------------------------------------------------------------------------


def test_render_report_no_findings_states_how_prefixes_were_resolved() -> None:
    report = audit_pull_requests(prs=[_pr(author=_FACTORY)], policy=_policy())
    text = render_report(report=report, policy=_policy())
    assert "No factory bypasses found" in text
    assert "Scanned 1 recently-merged PR(s)." in text
    assert "Product prefixes (declared): .claude-plugin/scripts/" in text


def test_render_report_with_findings() -> None:
    report = audit_pull_requests(prs=[_pr(number=7)], policy=_policy())
    text = render_report(report=report, policy=_policy())
    assert "Flagged 1 product-code PR(s)" in text
    assert "- PR #7 by @thewoolleyman" in text
    assert f"    - {_PRODUCT}" in text
    assert "Factory-Override exception" not in text


def test_render_report_lists_recorded_exceptions() -> None:
    report = audit_pull_requests(
        prs=[_pr(number=21, commit_messages=("fix: y\nFactory-Override: red master",))],
        policy=_policy(),
    )
    text = render_report(report=report, policy=_policy())
    assert "Recorded 1 Factory-Override exception(s):" in text
    assert "- PR #21 by @thewoolleyman" in text


def test_render_json_shape() -> None:
    report = audit_pull_requests(prs=[_pr(number=7)], policy=_policy())
    payload = json.loads(render_json(report=report, policy=_policy()))
    assert payload["scanned"] == 1
    assert payload["count"] == 1
    assert payload["factory_app_login"] == _FACTORY
    assert payload["findings"][0]["number"] == 7
    assert payload["findings"][0]["product_paths"] == [_PRODUCT]
    assert payload["product_prefixes_origin"] == "declared"
    assert ".claude-plugin/scripts/bin/" in payload["product_prefixes"]
    assert payload["exception_count"] == 0
    assert payload["exceptions"] == []


def test_render_json_empty() -> None:
    report = audit_pull_requests(prs=[], policy=_policy())
    payload = json.loads(render_json(report=report, policy=_policy()))
    assert payload["count"] == 0
    assert payload["findings"] == []


def test_render_json_carries_recorded_exceptions() -> None:
    report = audit_pull_requests(
        prs=[_pr(number=31, commit_messages=("fix: y\nFactory-Override: red master",))],
        policy=_policy(),
    )
    payload = json.loads(render_json(report=report, policy=_policy()))
    assert payload["exception_count"] == 1
    assert payload["exceptions"] == [
        {"number": 31, "title": "feat: change", "author": "thewoolleyman"}
    ]


# --------------------------------------------------------------------------
# main — the CLI supervisor
# --------------------------------------------------------------------------


def _stdout_one_bypass(*, path: str = _PRODUCT) -> str:
    return json.dumps(
        [
            {
                "number": 55,
                "title": "feat: sneaky",
                "author": {"login": "thewoolleyman"},
                "files": [{"path": path}],
                "labels": [],
                "commits": [],
            }
        ]
    )


def test_main_human_output(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(argv=[], seam=_seam(prs_stdout=_stdout_one_bypass()))
    assert code == 0
    out = capsys.readouterr().out
    assert "# Factory-Bypass Audit" in out
    assert "- PR #55 by @thewoolleyman" in out


def test_main_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(argv=["--json"], seam=_seam(prs_stdout=_stdout_one_bypass()))
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1


def test_main_repo_selects_the_layout_the_classifier_derives(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--repo` drives BOTH gh reads, so another repo's product code is visible."""
    code = main(
        argv=["--json", "--repo", "thewoolleyman/livespec-dev-tooling"],
        seam=_seam(
            prs_stdout=_stdout_one_bypass(path=_DEV_TOOLING_PRODUCT),
            pyproject=_DEV_TOOLING_PYPROJECT,
        ),
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["product_prefixes"] == ["livespec_dev_tooling/"]
    assert payload["findings"][0]["product_paths"] == [_DEV_TOOLING_PRODUCT]


def test_main_product_prefix_override(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        argv=["--json", "--product-prefix", "nowhere/"],
        seam=_seam(prs_stdout=_stdout_one_bypass()),
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["product_prefixes_origin"] == "operator-override"
    assert payload["count"] == 0


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
                "commits": [],
            }
        ]
    )
    code = main(
        argv=["--json", "--factory-app-login", "someone-else"],
        seam=_seam(prs_stdout=stdout),
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["count"] == 1
    assert payload["findings"][0]["author"] == _FACTORY


def test_main_allow_author_and_label(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        argv=["--json", "--allow-author", "thewoolleyman"],
        seam=_seam(prs_stdout=_stdout_one_bypass()),
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["count"] == 0


def test_main_threads_limit_and_since_and_one_repo_to_both_gh_reads(
    capsys: pytest.CaptureFixture[str],
) -> None:
    recorder: list[list[str]] = []
    code = main(
        argv=["--limit", "5", "--merged-since", "2026-07-01", "--repo", "o/r"],
        seam=_seam(prs_stdout="[]", recorder=recorder),
    )
    assert code == 0
    declaration, window = recorder
    assert declaration[1] == "repos/o/r/contents/pyproject.toml"
    assert window[window.index("--repo") + 1] == "o/r"
    assert window[window.index("--limit") + 1] == "5"
    assert window[window.index("--search") + 1] == "merged:>=2026-07-01"
    assert "No factory bypasses found" in capsys.readouterr().out


def test_default_factory_app_login_tracks_renamed_fleet_app() -> None:
    assert DEFAULT_FACTORY_APP_LOGIN == "app/thewoolleyman-factory-bot"
