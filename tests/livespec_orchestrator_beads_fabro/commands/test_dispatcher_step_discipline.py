"""Focused tests for the closed step vocabulary, its waivers, and its persistence.

Covers the four private modules the pre-dispatch step gate is built from: the
step-id vocabulary, the committed `dispatcher.step_waivers` reader, the
`janitor-bootstrap` integration-point re-verification, and the journal scan that
makes a degraded post-merge outcome persist across dispatches.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_step_gate
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_install_recipe import (
    JANITOR_BOOTSTRAP_KEY,
    hook_install_recipe_present,
    integration_point,
    janitor_bootstrap_recipe_from_block,
    remedy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import invoker_from_args
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_gate import (
    step_discipline_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_ids import (
    JANITOR_BOOTSTRAP,
    MASTER_CI,
    SOURCE_CHECKOUT,
    STEP_IDS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_persistence import (
    clearing_record,
    outstanding_degraded_step,
    persistence_refusal_detail,
    persistence_refusal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_step_waivers import (
    STEP_WAIVERS_KEY,
    StepWaiver,
    resolve_step_waivers,
    step_waivers_from_block,
    waived_proceed_detail,
    waived_proceed_record,
    waiver_for,
)

_DEFAULT_BRANCH = "trunk"
# The fleet convention, rendered from the resolver's own default so these
# fixtures cannot drift from the recipe they stand for.
_DEFAULT_RECIPE = janitor_bootstrap_recipe_from_block(block={})
INTEGRATION_POINT = integration_point(recipe=_DEFAULT_RECIPE)
REMEDY = remedy(recipe=_DEFAULT_RECIPE)


@dataclass(kw_only=True)
class _Runner:
    """Argv-keyed command stand-in for BOTH pre-dispatch preflights."""

    results: dict[tuple[str, ...], CommandResult]
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
        _ = (cwd, timeout_seconds, env, stdin)
        key = tuple(argv)
        self.calls.append(key)
        return self.results.get(key, CommandResult(exit_code=1, stdout="", stderr="unscripted"))


def _ok(*, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=0, stdout=stdout, stderr="")


def _green_preflight_results() -> dict[tuple[str, ...], CommandResult]:
    """Both pre-dispatch steps answering PASS, so the persistence arm is reachable."""
    return {
        ("git", "rev-parse", "--is-inside-work-tree"): _ok(stdout="true\n"),
        (
            "git",
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/remotes/origin",
        ): _ok(stdout=f"origin/{_DEFAULT_BRANCH}\n"),
        ("git", "rev-parse", "HEAD"): _ok(stdout="abc1234\n"),
        (
            "git",
            "merge-base",
            "--is-ancestor",
            "abc1234",
            f"origin/{_DEFAULT_BRANCH}",
        ): _ok(),
        ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): _ok(
            stdout=f"origin/{_DEFAULT_BRANCH}\n"
        ),
        ("gh", "auth", "token"): _ok(stdout="secret\n"),
        (
            "gh",
            "run",
            "list",
            "--branch",
            _DEFAULT_BRANCH,
            "--limit",
            "1",
            "--workflow",
            "CI",
            "--json",
            "status,conclusion,databaseId",
        ): _ok(
            stdout=json.dumps([{"status": "completed", "conclusion": "success", "databaseId": 42}])
        ),
        ("gh", "run", "view", "42", "--json", "jobs"): _ok(
            stdout=json.dumps(
                {"jobs": [{"name": "ci-green", "conclusion": "success", "status": "completed"}]}
            )
        ),
    }


def _repo(*, tmp_path: Path, dispatcher: str = "") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}'
        f"{dispatcher}}}}}",
        encoding="utf-8",
    )
    return repo


def _degraded_line(*, at: str = "2026-08-28T00:00:00Z", item: str = "bd-ib-1") -> str:
    return json.dumps(
        {
            "stage": "outcome",
            "at": at,
            "invoker": "session:x",
            "invoker_source": "env",
            "outcome": {
                "work_item_id": item,
                "status": "green",
                "stage": "janitor-env-degraded",
                "step": JANITOR_BOOTSTRAP,
                "missing_integration_point": INTEGRATION_POINT,
                "remedy": REMEDY,
            },
        }
    )


def _args(*, journal: Path) -> argparse.Namespace:
    return argparse.Namespace(journal=str(journal), invoker=None)


def _run_gate(
    *, repo: Path, journal: Path, runner: _Runner, monkeypatch: pytest.MonkeyPatch
) -> str | None:
    monkeypatch.setattr(_dispatcher_step_gate, "ShellCommandRunner", lambda: runner)
    return step_discipline_refusal(
        args=_args(journal=journal),
        repo=repo,
        identity=invoker_from_args(args=argparse.Namespace(invoker=None)),
    )


def _records(*, journal: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------------------
# The closed vocabulary
# ---------------------------------------------------------------------------


def test_the_step_vocabulary_is_exactly_the_three_ratified_identifiers() -> None:
    """Extensible only by ratification: a fourth id is a spec change, not a literal."""
    assert STEP_IDS == (SOURCE_CHECKOUT, MASTER_CI, JANITOR_BOOTSTRAP)


# ---------------------------------------------------------------------------
# Committed waivers
# ---------------------------------------------------------------------------


def test_a_well_formed_waiver_entry_is_read_from_the_committed_block() -> None:
    waivers = step_waivers_from_block(
        block={
            "step_waivers": [
                {"step": MASTER_CI, "owner": "alice", "reason": "no forge on this host"}
            ]
        }
    )

    assert waivers == (StepWaiver(step=MASTER_CI, owner="alice", reason="no forge on this host"),)
    assert waiver_for(waivers=waivers, step=MASTER_CI) is not None
    # A waiver is scoped to its named step ONLY.
    assert waiver_for(waivers=waivers, step=SOURCE_CHECKOUT) is None


@pytest.mark.parametrize(
    "entry",
    [
        pytest.param("master-ci", id="not-a-mapping"),
        pytest.param({"owner": "alice", "reason": "why"}, id="no-step"),
        pytest.param({"step": 7, "owner": "alice", "reason": "why"}, id="non-string-step"),
        pytest.param(
            {"step": "invented-step", "owner": "alice", "reason": "why"},
            id="step-outside-the-closed-vocabulary",
        ),
        pytest.param({"step": MASTER_CI, "reason": "why"}, id="no-owner"),
        pytest.param({"step": MASTER_CI, "owner": "", "reason": "why"}, id="empty-owner"),
        pytest.param({"step": MASTER_CI, "owner": "alice"}, id="no-reason"),
        pytest.param({"step": MASTER_CI, "owner": "alice", "reason": ""}, id="empty-reason"),
    ],
)
def test_a_defective_waiver_entry_relaxes_nothing(entry: object) -> None:
    """Fail-closed: a typo in a waiver must not read as a disarmed safety gate."""
    assert step_waivers_from_block(block={"step_waivers": [entry]}) == ()


@pytest.mark.parametrize(
    "block",
    [pytest.param({}, id="absent-key"), pytest.param({"step_waivers": {}}, id="not-a-list")],
)
def test_an_absent_or_malformed_waivers_key_waives_nothing(block: dict[str, object]) -> None:
    assert step_waivers_from_block(block=block) == ()


def test_waivers_resolve_from_the_committed_livespec_jsonc(tmp_path: Path) -> None:
    repo = _repo(
        tmp_path=tmp_path,
        dispatcher=(
            ', "dispatcher": {"step_waivers": [{"step": "source-checkout", '
            '"owner": "ops", "reason": "export-only mirror"}]}'
        ),
    )

    assert resolve_step_waivers(cwd=repo) == (
        StepWaiver(step=SOURCE_CHECKOUT, owner="ops", reason="export-only mirror"),
    )


def test_a_waived_proceed_journals_the_owner_and_what_it_waived() -> None:
    waiver = StepWaiver(step=MASTER_CI, owner="alice", reason="air-gapped host")

    record = waived_proceed_record(waiver=waiver, waived={"reason": "master-ci-unprovable"})

    assert record["status"] == "waived"
    assert record["step"] == MASTER_CI
    assert record["waiver_owner"] == "alice"
    assert record["declaring_key"] == STEP_WAIVERS_KEY
    assert record["waived_outcome"] == {"reason": "master-ci-unprovable"}
    assert "alice" in waived_proceed_detail(waiver=waiver)


# ---------------------------------------------------------------------------
# The janitor-bootstrap integration point
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["justfile", "Justfile", ".justfile"])
def test_the_hook_install_recipe_is_observed_in_any_justfile_spelling(
    tmp_path: Path, name: str
) -> None:
    _ = (tmp_path / name).write_text(
        "default:\n    echo hi\n\ninstall-commit-refuse-hooks:\n    echo installed\n",
        encoding="utf-8",
    )

    assert hook_install_recipe_present(repo=tmp_path, recipe=_DEFAULT_RECIPE) is True


def test_a_recipe_mentioned_only_inside_a_body_is_not_a_declaration(tmp_path: Path) -> None:
    """Only a column-zero declaration counts; a mention in a body provides nothing."""
    _ = (tmp_path / "justfile").write_text(
        "bootstrap:\n    just install-commit-refuse-hooks\n", encoding="utf-8"
    )

    assert hook_install_recipe_present(repo=tmp_path, recipe=_DEFAULT_RECIPE) is False


def test_a_repository_with_no_justfile_at_all_does_not_provide_the_integration_point(
    tmp_path: Path,
) -> None:
    assert hook_install_recipe_present(repo=tmp_path, recipe=_DEFAULT_RECIPE) is False


def test_a_declared_just_recipe_is_re_verified_against_the_name_it_declares(
    tmp_path: Path,
) -> None:
    """Declaration changes WHAT is looked for: the fleet's own name is not looked for."""
    recipe = janitor_bootstrap_recipe_from_block(
        block={"janitor_bootstrap": {"recipe": "just hooks"}}
    )
    _ = (tmp_path / "justfile").write_text("hooks:\n    echo installed\n", encoding="utf-8")

    assert hook_install_recipe_present(repo=tmp_path, recipe=recipe) is True
    assert hook_install_recipe_present(repo=tmp_path, recipe=_DEFAULT_RECIPE) is False


def test_a_flag_before_the_recipe_name_does_not_hide_the_declaration(tmp_path: Path) -> None:
    """`just` takes options before its recipes; over-collecting candidates absorbs them."""
    recipe = janitor_bootstrap_recipe_from_block(
        block={"janitor_bootstrap": {"recipe": "just --justfile build.just hooks"}}
    )
    _ = (tmp_path / "justfile").write_text("hooks:\n    echo installed\n", encoding="utf-8")

    assert hook_install_recipe_present(repo=tmp_path, recipe=recipe) is True


def test_an_adopter_script_shipped_by_the_repository_is_invokable(tmp_path: Path) -> None:
    """A non-`just` recipe has no declaration surface, so it is answered by invokability."""
    recipe = janitor_bootstrap_recipe_from_block(
        block={"janitor_bootstrap": {"recipe": "./install-hooks.sh --force"}}
    )
    script = tmp_path / "install-hooks.sh"
    _ = script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    assert hook_install_recipe_present(repo=tmp_path, recipe=recipe) is False

    script.chmod(0o755)
    assert hook_install_recipe_present(repo=tmp_path, recipe=recipe) is True


def test_a_recipe_whose_program_is_on_path_is_invokable(tmp_path: Path) -> None:
    recipe = janitor_bootstrap_recipe_from_block(
        block={"janitor_bootstrap": {"recipe": "sh -c 'install hooks'"}}
    )

    assert hook_install_recipe_present(repo=tmp_path, recipe=recipe) is True


def test_a_recipe_naming_a_program_that_exists_nowhere_is_unresolvable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    recipe = janitor_bootstrap_recipe_from_block(
        block={"janitor_bootstrap": {"recipe": "hook-installer-9000"}}
    )

    assert hook_install_recipe_present(repo=tmp_path, recipe=recipe) is False


def test_a_defective_declaration_resolves_nothing_and_so_provides_nothing(
    tmp_path: Path,
) -> None:
    """There is no command to look for, so no repository state could ever satisfy it."""
    recipe = janitor_bootstrap_recipe_from_block(block={"janitor_bootstrap": "just hooks"})
    _ = (tmp_path / "justfile").write_text(
        "install-commit-refuse-hooks:\n    echo installed\n", encoding="utf-8"
    )

    assert recipe.defect is not None
    assert hook_install_recipe_present(repo=tmp_path, recipe=recipe) is False


# ---------------------------------------------------------------------------
# Cross-dispatch persistence of a degraded outcome
# ---------------------------------------------------------------------------


def test_an_absent_journal_carries_no_outstanding_degradation(tmp_path: Path) -> None:
    assert outstanding_degraded_step(journal_path=tmp_path / "nope.jsonl") is None


def test_an_unreadable_journal_carries_no_outstanding_degradation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A journal that exists but will not read is unreadable, not a degradation.

    Fail-OPEN here on purpose, and only here: an unreadable journal cannot
    establish that a degradation stands, and refusing every dispatch on a
    transient read error would strand the repository on evidence nobody has.
    """
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(_degraded_line() + "\n", encoding="utf-8")

    def _refuse_to_read(*args: object, **kwargs: object) -> str:
        _ = (args, kwargs)
        raise OSError("journal unreadable")

    monkeypatch.setattr(Path, "read_text", _refuse_to_read)

    assert outstanding_degraded_step(journal_path=journal) is None


def test_unparseable_and_irrelevant_lines_are_skipped(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(
        "\n".join(
            (
                "{not json at all",
                json.dumps(["a list, not a record"]),
                json.dumps({"stage": "ledger-admit"}),
                json.dumps({"stage": "outcome", "outcome": "not a mapping"}),
                json.dumps({"stage": "outcome", "at": "t", "outcome": {"step": "invented"}}),
                json.dumps(
                    {
                        "stage": "outcome",
                        "at": "t",
                        "outcome": {"step": JANITOR_BOOTSTRAP, "remedy": REMEDY},
                    }
                ),
            )
        ),
        encoding="utf-8",
    )

    assert outstanding_degraded_step(journal_path=journal) is None


def test_a_degraded_outcome_is_read_back_with_its_durable_reference(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(_degraded_line(), encoding="utf-8")

    degraded = outstanding_degraded_step(journal_path=journal)

    assert degraded is not None
    assert degraded.step == JANITOR_BOOTSTRAP
    assert degraded.work_item_id == "bd-ib-1"
    assert degraded.reference == (
        "stage=outcome at=2026-08-28T00:00:00Z work_item_id=bd-ib-1 step=janitor-bootstrap"
    )
    assert degraded.missing_integration_point == INTEGRATION_POINT
    refusal = persistence_refusal_record(degraded=degraded)
    assert refusal["originating_outcome_record"] == degraded.reference
    detail = persistence_refusal_detail(degraded=degraded)
    assert degraded.reference in detail
    assert INTEGRATION_POINT in detail


def test_an_outcome_missing_its_stamped_at_still_renders_a_reference(tmp_path: Path) -> None:
    """A record with no envelope stamp is still addressable, by an explicit marker."""
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(
        json.dumps(
            {
                "stage": "outcome",
                "outcome": {
                    "step": JANITOR_BOOTSTRAP,
                    "missing_integration_point": INTEGRATION_POINT,
                    "remedy": REMEDY,
                },
            }
        ),
        encoding="utf-8",
    )

    degraded = outstanding_degraded_step(journal_path=journal)

    assert degraded is not None
    assert degraded.at == "<unknown>"
    assert degraded.work_item_id == "<unknown>"


def test_a_clearing_record_ends_the_persistence_of_the_record_it_names(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    first = outstanding_degraded_step(
        journal_path=_write(path=journal, lines=[_degraded_line(at="t1")])
    )
    assert first is not None

    _ = _write(
        path=journal,
        lines=[_degraded_line(at="t1"), json.dumps(clearing_record(degraded=first))],
    )
    assert outstanding_degraded_step(journal_path=journal) is None

    # A LATER degradation is a new one and refuses again on its own account.
    _ = _write(
        path=journal,
        lines=[
            _degraded_line(at="t1"),
            json.dumps(clearing_record(degraded=first)),
            _degraded_line(at="t2"),
        ],
    )
    again = outstanding_degraded_step(journal_path=journal)
    assert again is not None
    assert again.at == "t2"


def _write(*, path: Path, lines: list[str]) -> Path:
    _ = path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------


def test_the_gate_proceeds_and_journals_both_passes_when_nothing_is_outstanding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = tmp_path / "journal.jsonl"

    refusal = _run_gate(
        repo=repo,
        journal=journal,
        runner=_Runner(results=_green_preflight_results()),
        monkeypatch=monkeypatch,
    )

    assert refusal is None
    assert [record["step"] for record in _records(journal=journal)] == [
        SOURCE_CHECKOUT,
        MASTER_CI,
    ]


def test_a_refusing_first_step_stops_the_sequence_before_the_forge_is_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lazy evaluation is the point: a refused dispatch spends no network."""
    repo = _repo(tmp_path=tmp_path)
    journal = tmp_path / "journal.jsonl"
    runner = _Runner(results={})

    refusal = _run_gate(repo=repo, journal=journal, runner=runner, monkeypatch=monkeypatch)

    assert refusal is not None
    assert "not a Git worktree" in refusal
    assert [call for call in runner.calls if call[0] == "gh"] == []
    assert [record["step"] for record in _records(journal=journal)] == [SOURCE_CHECKOUT]


def test_a_committed_waiver_lets_a_failing_preflight_step_proceed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(
        tmp_path=tmp_path,
        dispatcher=(
            ', "dispatcher": {"step_waivers": [{"step": "source-checkout", '
            '"owner": "ops", "reason": "read-only export mirror"}]}'
        ),
    )
    journal = tmp_path / "journal.jsonl"
    results = _green_preflight_results()
    del results[("git", "rev-parse", "--is-inside-work-tree")]

    refusal = _run_gate(
        repo=repo,
        journal=journal,
        runner=_Runner(results=results),
        monkeypatch=monkeypatch,
    )

    assert refusal is None
    records = _records(journal=journal)
    assert [record["status"] for record in records] == ["failed", "waived", "passed"]
    assert records[1]["waiver_owner"] == "ops"
    assert "ops" in capsys.readouterr().err


def test_an_outstanding_degradation_refuses_the_next_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(_degraded_line() + "\n", encoding="utf-8")

    refusal = _run_gate(
        repo=repo,
        journal=journal,
        runner=_Runner(results=_green_preflight_results()),
        monkeypatch=monkeypatch,
    )

    assert refusal is not None
    assert INTEGRATION_POINT in refusal
    assert _records(journal=journal)[-1]["reason"] == "degraded-step-outcome-persists"


def test_a_passing_re_verification_clears_the_degradation_and_proceeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = (repo / "justfile").write_text(
        "install-commit-refuse-hooks:\n    echo installed\n", encoding="utf-8"
    )
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(_degraded_line() + "\n", encoding="utf-8")

    refusal = _run_gate(
        repo=repo,
        journal=journal,
        runner=_Runner(results=_green_preflight_results()),
        monkeypatch=monkeypatch,
    )

    assert refusal is None
    clearing = _records(journal=journal)[-1]
    assert clearing["stage"] == "step-clearing"
    assert clearing["step"] == JANITOR_BOOTSTRAP
    assert clearing["clears_outcome_at"] == "2026-08-28T00:00:00Z"


def test_a_waiver_on_the_degraded_step_proceeds_without_clearing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A waiver relaxes each dispatch; it never pretends the integration point arrived."""
    repo = _repo(
        tmp_path=tmp_path,
        dispatcher=(
            ', "dispatcher": {"step_waivers": [{"step": "janitor-bootstrap", '
            '"owner": "carol", "reason": "adopter migrating off just"}]}'
        ),
    )
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(_degraded_line() + "\n", encoding="utf-8")

    refusal = _run_gate(
        repo=repo,
        journal=journal,
        runner=_Runner(results=_green_preflight_results()),
        monkeypatch=monkeypatch,
    )

    assert refusal is None
    waived = _records(journal=journal)[-1]
    assert waived["status"] == "waived"
    assert waived["waiver_owner"] == "carol"
    assert outstanding_degraded_step(journal_path=journal) is not None


def test_a_degraded_pre_dispatch_step_is_re_verified_by_its_own_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A step that verifies itself every dispatch clears on the pass it just produced."""
    repo = _repo(tmp_path=tmp_path)
    journal = tmp_path / "journal.jsonl"
    degraded = json.loads(_degraded_line())
    degraded["outcome"]["step"] = MASTER_CI
    _ = journal.write_text(json.dumps(degraded) + "\n", encoding="utf-8")

    refusal = _run_gate(
        repo=repo,
        journal=journal,
        runner=_Runner(results=_green_preflight_results()),
        monkeypatch=monkeypatch,
    )

    assert refusal is None
    assert _records(journal=journal)[-1]["step"] == MASTER_CI
    assert _records(journal=journal)[-1]["stage"] == "step-clearing"
    # A step that verifies itself carries no declared resolution to report, so
    # the refusal record stays exactly as it was before v087 for those steps.
    assert "resolution_attempted" not in _records(journal=journal)[-1]


def test_the_janitor_bootstrap_refusal_names_the_resolution_and_the_declaring_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An undeclared key resolves against the convention, and SAYS that it did."""
    repo = _repo(tmp_path=tmp_path)
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(_degraded_line() + "\n", encoding="utf-8")

    refusal = _run_gate(
        repo=repo,
        journal=journal,
        runner=_Runner(results=_green_preflight_results()),
        monkeypatch=monkeypatch,
    )

    assert refusal is not None
    assert "Resolution attempted: default convention" in refusal
    assert "just install-commit-refuse-hooks" in refusal
    assert JANITOR_BOOTSTRAP_KEY in refusal
    assert JANITOR_BOOTSTRAP_KEY in str(_records(journal=journal)[-1]["resolution_attempted"])


def test_a_declared_recipe_the_repository_provides_clears_the_degradation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The adopter route: no fleet recipe anywhere, and the degradation still clears."""
    repo = _repo(
        tmp_path=tmp_path,
        dispatcher=', "dispatcher": {"janitor_bootstrap": {"recipe": "./install-hooks.sh"}}',
    )
    script = repo / "install-hooks.sh"
    _ = script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(_degraded_line() + "\n", encoding="utf-8")

    refusal = _run_gate(
        repo=repo,
        journal=journal,
        runner=_Runner(results=_green_preflight_results()),
        monkeypatch=monkeypatch,
    )

    assert refusal is None
    assert _records(journal=journal)[-1]["stage"] == "step-clearing"


def test_a_declared_recipe_the_repository_does_not_provide_refuses_naming_the_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A present-but-unusable declaration never slides onto the convention."""
    repo = _repo(
        tmp_path=tmp_path,
        dispatcher=', "dispatcher": {"janitor_bootstrap": {"owner": "dana"}}',
    )
    _ = (repo / "justfile").write_text(
        "install-commit-refuse-hooks:\n    echo installed\n", encoding="utf-8"
    )
    journal = tmp_path / "journal.jsonl"
    _ = journal.write_text(_degraded_line() + "\n", encoding="utf-8")

    refusal = _run_gate(
        repo=repo,
        journal=journal,
        runner=_Runner(results=_green_preflight_results()),
        monkeypatch=monkeypatch,
    )

    assert refusal is not None
    assert "Resolution attempted: declared" in refusal
    assert f"`{JANITOR_BOOTSTRAP_KEY}.recipe` is absent" in refusal
