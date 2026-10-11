"""Integration-tier acceptance for Scenario 130's Fabro currency admission.

Binds `SPECIFICATION/scenarios.md` "Scenario 130 — Dispatch admits only a
current, identifiable Fabro base" and the Fabro-currency-admission clause of
`SPECIFICATION/contracts.md`, through the REAL pre-dispatch wall,
`_dispatcher_pre_dispatch_wall.pre_dispatch_wall_exit`: the real committed
`.livespec.jsonc` factory block, the real `JournalFile` on disk, the real
release-observation cache under a tmp `XDG_STATE_HOME`, and the real forge and
engine argvs. Only the `CommandRunner` that shells out to `gh` and `fabro`, and
the clock the observation is aged against, are stood in.

DRIVING THE WALL RATHER THAN THE GATE is what makes "refused BEFORE claim"
observable. The wall is the one sequence both dispatch paths run after selection
and before admission, so a refusal returning from it is a refusal that reached no
`admit_and_select`: nothing moved `ready -> active`, no assignee was set and no
Fabro run was created. A gate-level assertion that a verdict carries a refusal
cannot show that.

THE CURRENCY GATE IS FIRST IN THE WALL, and that is why these cases need no
fixture for the criteria wall, the proof-assets prerelease, the proof-credential
declaration or the host Codex credential: a refusal here returns before any of
them runs. That ordering is itself load-bearing rather than convenient — the
proof-assets gate CREATES a repository prerelease and the Codex gate SPENDS a
bounded provider renewal, so an engine that cannot be admitted at all must be
refused ahead of both.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_fabro_currency_gate as gate
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_fabro_currency_sources as sources,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    EXIT_PRECONDITION_ERROR,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency import (
    CONDITION_OUT_OF_WINDOW,
    CURRENCY_WINDOW_DAYS,
    FABRO_UPSTREAM_REPO,
    OBSERVATION_MAX_AGE_DAYS,
    FabroRelease,
    FabroReleaseObservation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_release_cache import (
    release_observation_path,
    write_release_observation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_pre_dispatch_wall import (
    pre_dispatch_wall_exit,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import WorkItem

_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"
_TARGET = "hp"
_TARGET_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_FABRO_BIN = "/home/ubuntu/.fabro/bin/fabro"
_SERVING_COMMIT = "8869e88"
# The ordinary out-of-window base is deliberately NOT the 0.254 carrier. The one
# ratified exception covers that series specifically, so an out-of-window case
# built on it would pass only for as long as the exception went unimplemented —
# and would then start reporting an admitted transition as a refusal.
_BASE_TAG = "v0.300.0"
_BASE_PUBLISHED = "2026-07-30T12:00:00Z"
# The carrier the one non-renewable transition admits, and its own publication
# time: far enough behind the newest release to be out of window on the ordinary
# rule, which is what makes the exception the only thing that can admit it.
_CARRIER_TAG = "v0.254.0"
_CARRIER_PUBLISHED = "2026-07-30T12:00:00Z"
_NEWEST_TAG = "v0.378.0-nightly.0"
_NEWEST_PUBLISHED = "2026-10-10T01:00:00Z"
_NOW = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)
# The ratified instant the transition expires at, to the second.
_DEADLINE = datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc)
# Every stage this gate writes shares this prefix, which is what lets a case
# read ITS records out of a journal the rest of the wall also writes to.
_CURRENCY_STAGE_PREFIX = "dispatcher-fabro-currency-"

# THE RELEASE-CLASS FIXTURE, built so that publication order, enumeration order
# and semantic-version order all DISAGREE. The stable `v0.400.0` is highest by
# semver and FIRST in the forge's own enumeration, yet it was published five
# weeks before the `v0.378.0-nightly.0` prerelease — so a reading that took
# either the list head or the highest version would pick it as the newest
# release, and the only thing that picks the nightly is publication time.
_SEMVER_HIGHEST_TAG = "v0.400.0"
_SEMVER_HIGHEST_PUBLISHED = "2026-09-01T00:00:00Z"
_PUBLISHED_NEWEST_TAG = "v0.378.0-nightly.0"
_PUBLISHED_NEWEST_PUBLISHED = "2026-10-10T00:00:00Z"
_RELEASE_CLASS_BASE_TAG = "v0.390.0"
_RELEASE_CLASS_BASE_PUBLISHED = "2026-09-05T00:00:00Z"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


@dataclass(kw_only=True)
class _Runner:
    """Stands in for the two shelling-out seams: `gh api` and `fabro version`."""

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
        del cwd, timeout_seconds, env, stdin
        key = tuple(argv)
        self.calls.append(key)
        return self.results.get(key, CommandResult(exit_code=1, stdout="", stderr="unstubbed"))


def _version_text() -> str:
    """`fabro version`'s own two-section form, as the pinned engine prints it."""
    return (
        f"Client: fabro 0.254.0 ({_SERVING_COMMIT} 2026-07-30)\n"
        f"Server: fabro 0.254.0 ({_SERVING_COMMIT} 2026-08-02) at {_TARGET_SERVER}\n"
    )


def _releases_payload(*, releases: list[tuple[str, str]]) -> str:
    """What `gh api --paginate --jq '.[] | {tag, published_at}'` actually emits.

    One compact object per LINE, not one array: the production argv carries that
    projection precisely because `--paginate` concatenates one array per page, so
    a fixture emitting a single array would exercise a reader the real forge
    answer never reaches.
    """
    return (
        "\n".join(
            json.dumps({"tag": tag, "published_at": published}) for tag, published in releases
        )
        + "\n"
    )


def _runner(*, releases: list[tuple[str, str]], ancestors: frozenset[str]) -> _Runner:
    """The two stood-in seams, answering exactly what this case needs them to.

    Every parameter is REQUIRED rather than defaulted. A default here is an arm
    no case takes, and this tier's per-file coverage gate reads a never-taken
    branch in a fixture exactly as it reads one in the product.
    """
    results: dict[tuple[str, ...], CommandResult] = {
        tuple(sources.releases_argv()): CommandResult(
            exit_code=0, stdout=_releases_payload(releases=releases), stderr=""
        ),
        (_FABRO_BIN, "version"): CommandResult(exit_code=0, stdout=_version_text(), stderr=""),
    }
    for tag, _published in releases:
        status = "ahead" if tag in ancestors else "diverged"
        results[tuple(sources.compare_argv(base=tag, head=_SERVING_COMMIT))] = CommandResult(
            exit_code=0, stdout=f"{status}\n", stderr=""
        )
    return _Runner(results=results)


def _observed_releases() -> list[tuple[str, str]]:
    """The newest release and the 0.254 carrier, in the forge's own order."""
    return [(_NEWEST_TAG, _NEWEST_PUBLISHED), (_BASE_TAG, _BASE_PUBLISHED)]


def _refresh_failure_runner() -> _Runner:
    """The releases read FAILS; the engine and the ancestry comparison succeed.

    Shaped so the only thing wrong is the refresh: if the gate were to fall back
    on a cached observation it would find an identifiable serving build, a
    resolvable base and a base comfortably inside the window — i.e. it would
    ADMIT. That is what makes the refusal evidence of the staleness rule rather
    than of some unrelated fault.
    """
    results: dict[tuple[str, ...], CommandResult] = {
        tuple(sources.releases_argv()): CommandResult(exit_code=1, stdout="", stderr="HTTP 503"),
        (_FABRO_BIN, "version"): CommandResult(exit_code=0, stdout=_version_text(), stderr=""),
        tuple(sources.compare_argv(base=_BASE_TAG, head=_SERVING_COMMIT)): CommandResult(
            exit_code=0, stdout="ahead\n", stderr=""
        ),
        tuple(sources.compare_argv(base=_NEWEST_TAG, head=_SERVING_COMMIT)): CommandResult(
            exit_code=0, stdout="diverged\n", stderr=""
        ),
    }
    return _Runner(results=results)


def _release_class_releases() -> list[tuple[str, str]]:
    """The three-release fixture, in the forge's own enumeration order."""
    return [
        (_SEMVER_HIGHEST_TAG, _SEMVER_HIGHEST_PUBLISHED),
        (_PUBLISHED_NEWEST_TAG, _PUBLISHED_NEWEST_PUBLISHED),
        (_RELEASE_CLASS_BASE_TAG, _RELEASE_CLASS_BASE_PUBLISHED),
    ]


def _carrier_releases() -> list[tuple[str, str]]:
    """The newest release and the 0.254 carrier, in the forge's own order."""
    return [(_NEWEST_TAG, _NEWEST_PUBLISHED), (_CARRIER_TAG, _CARRIER_PUBLISHED)]


def _seed_stale_cache(*, age_days: int) -> FabroReleaseObservation:
    """A cached observation `age_days` old that would otherwise admit the build.

    Written through the PRODUCTION writer rather than hand-authored JSON, so the
    record the gate reads back is the record the gate itself writes.
    """
    observation = FabroReleaseObservation(
        releases=(
            FabroRelease(tag=_NEWEST_TAG, published_at=_NOW - timedelta(days=age_days + 1)),
            FabroRelease(tag=_BASE_TAG, published_at=_NOW - timedelta(days=age_days + 6)),
        ),
        observed_at=_NOW - timedelta(days=age_days),
    )
    write_release_observation(path=release_observation_path(), observation=observation)
    return observation


def _install(*, monkeypatch: pytest.MonkeyPatch, runner: _Runner, now: datetime) -> None:
    """Stand in the ONLY two things that leave the process: the shell and the clock."""
    monkeypatch.setattr(gate, "ShellCommandRunner", lambda: runner)
    monkeypatch.setattr(gate, "currency_instant", lambda: now)


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    workflow = repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text("[workflow]\n", encoding="utf-8")
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                _PLUGIN_NAME: {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "default_factory": _TARGET,
                        "factories": {
                            _TARGET: {"server": _TARGET_SERVER, "bin": _FABRO_BIN},
                        },
                    },
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return repo


def _item() -> WorkItem:
    return replace(
        WorkItem(
            id="bd-ib-j9x",
            type="task",
            status="ready",
            title="A ready task",
            description=(
                "## Definition of Done\n"
                "\n"
                "- The dispatched slice lands its change.\n"
                "\n"
                "References: ## Scenario 130 — Dispatch admits only a current,"
                " identifiable Fabro base\n"
            ),
            origin="freeform",
            gap_id=None,
            rank="a2",
            assignee=None,
            depends_on=(),
            captured_at="2026-10-10T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
            admission_policy="auto",
            acceptance_policy="ai-only",
            acceptance_criteria="The dispatched slice is verified green by the check suite.",
        )
    )


def _wall_exit(*, repo: Path, journal_path: Path) -> int | None:
    """Seed the selection through the store seam, then run the REAL wall over it.

    The item is written through `append_work_item` rather than handed to the wall
    alone because the gate resolves each item's recorded factory pin out of the
    tenant: a selection the tenant does not hold would exercise the degraded
    no-pin arm instead of the ordinary one every real dispatch takes.
    """
    item = _item()
    append_work_item(path=store_config(repo=repo), item=item)
    args = argparse.Namespace(
        workflow=str(repo / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"),
        workflow_name=None,
        journal=str(journal_path),
        repo=str(repo),
        factory=None,
        fabro_bin=_FABRO_BIN,
    )
    return pre_dispatch_wall_exit(
        args=args,
        repo=repo,
        items=[item],
        journal=JournalFile(path=journal_path),
    )


def _records(*, journal_path: Path) -> list[dict[str, object]]:
    """This gate's own journal records, in order.

    Deliberately NOT guarded into an empty list on a missing file: a missing
    journal would read identically to a journal carrying no currency record,
    which is half of what each of these cases asserts.

    FILTERED BY STAGE, because an ADMITTED dispatch goes on to run the rest of
    the wall and those gates journal too — so an unfiltered read is a list whose
    later entries carry no `condition` at all, and the obvious assertion raises
    `KeyError` on a sibling gate's perfectly correct record.
    """
    text = journal_path.read_text(encoding="utf-8")
    records = [json.loads(line) for line in text.splitlines() if line]
    return [record for record in records if str(record["stage"]).startswith(_CURRENCY_STAGE_PREFIX)]


def test_scenario130_an_out_of_window_base_refuses_before_claim_with_complete_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The 30-calendar-day window, refused with every piece of evidence named.

    The serving commit descends from an exact published release tag, so the base
    IS identifiable — what fails is the window, 72 calendar days wide against a
    30-day bound. The refusal has to name the target, the serving integration
    commit, the base and its publication time, the newest observed release and
    its publication time, the observation time, the failed condition and the
    corrective route, because an operator reading only "out of window" cannot
    tell which of those six facts to act on.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repo = _repo(tmp_path=tmp_path)
    _install(
        monkeypatch=monkeypatch,
        runner=_runner(releases=_observed_releases(), ancestors=frozenset({_BASE_TAG})),
        now=_NOW,
    )
    journal_path = tmp_path / "journal.jsonl"

    exit_code = _wall_exit(repo=repo, journal_path=journal_path)

    assert exit_code == EXIT_PRECONDITION_ERROR
    refusal = capsys.readouterr().err
    assert _TARGET in refusal
    assert _SERVING_COMMIT in refusal
    assert _BASE_TAG in refusal
    assert "2026-07-30T12:00:00+00:00" in refusal
    assert _NEWEST_TAG in refusal
    assert "2026-10-10T01:00:00+00:00" in refusal
    assert "2026-10-11T09:00:00+00:00" in refusal
    assert CONDITION_OUT_OF_WINDOW in refusal
    assert FABRO_UPSTREAM_REPO in refusal
    assert "re-pin" in refusal
    records = _records(journal_path=journal_path)
    assert [record["stage"] for record in records] == [gate.FABRO_CURRENCY_REFUSED_STAGE]
    assert records[0]["condition"] == CONDITION_OUT_OF_WINDOW
    assert records[0]["target"] == _TARGET


def test_scenario130_a_serving_commit_with_no_release_tag_ancestor_refuses_before_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A build whose ancestry matches NO published release tag has no valid base.

    The condition is asserted as the LITERAL journal string rather than through
    the imported constant, because that string is a durable record interface: a
    reader triaging the journal keys on it, and a rename that only moved a Python
    constant would leave every recorded row meaning something else.

    It has to be its OWN condition rather than a generic unobservable one. "No
    release-tag ancestor" and "the forge could not be read" refuse the same
    dispatch and have opposite remedies — one re-pins the engine onto a published
    tag, the other waits for the forge — so a single condition sends the operator
    to guess which they have. And the refusal states the SCOPE the ancestry walk
    searched, because an absence asserted over an unstated population is what
    turns a bounded search into a false impossibility.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repo = _repo(tmp_path=tmp_path)
    _install(
        monkeypatch=monkeypatch,
        runner=_runner(releases=_observed_releases(), ancestors=frozenset()),
        now=_NOW,
    )
    journal_path = tmp_path / "journal.jsonl"

    exit_code = _wall_exit(repo=repo, journal_path=journal_path)

    assert exit_code == EXIT_PRECONDITION_ERROR
    refusal = capsys.readouterr().err
    assert "no-release-tag-ancestor" in refusal
    assert "no published release-tag ancestor" in refusal
    assert str(sources.ANCESTRY_CANDIDATE_LIMIT) in refusal
    # The serving build IS identified here, which is what makes the missing base
    # the finding rather than an unreadable engine.
    assert _SERVING_COMMIT in refusal
    assert "  upstream base: unknown" in refusal
    records = _records(journal_path=journal_path)
    assert [record["condition"] for record in records] == ["no-release-tag-ancestor"]


def test_scenario130_a_stale_observation_whose_refresh_fails_refuses_before_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An expired reading is not evidence, however admissible it looks.

    The seeded cache is deliberately one that WOULD admit: its base sits six
    calendar days behind its newest release, well inside the thirty-day window,
    and the serving commit descends from it. So "the dispatch was refused" can
    only be the age rule firing — a build that served the stale record instead
    would have reported `current` and gone on to claim the item.

    The refusal NAMES the stale observation: its age, the bound it exceeded, and
    the instant it was taken. Without those an operator cannot tell a broken
    refresh path from a host that has never taken a reading, and the two have
    different remedies.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    stale = _seed_stale_cache(age_days=OBSERVATION_MAX_AGE_DAYS + 2)
    repo = _repo(tmp_path=tmp_path)
    _install(monkeypatch=monkeypatch, runner=_refresh_failure_runner(), now=_NOW)
    journal_path = tmp_path / "journal.jsonl"

    exit_code = _wall_exit(repo=repo, journal_path=journal_path)

    assert exit_code == EXIT_PRECONDITION_ERROR
    refusal = capsys.readouterr().err
    assert "release-observation-stale" in refusal
    assert f"{OBSERVATION_MAX_AGE_DAYS + 2} calendar days old" in refusal
    assert f"the bound is {OBSERVATION_MAX_AGE_DAYS}" in refusal
    assert "refreshing it failed" in refusal
    # The stale record is NAMED rather than merely declined.
    assert f"  release observation taken at: {stale.observed_at.isoformat()}" in refusal
    records = _records(journal_path=journal_path)
    assert [record["condition"] for record in records] == ["release-observation-stale"]


def test_scenario130_the_one_transition_admits_the_carrier_until_its_deadline_and_no_longer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exception and its expiry, over ONE fixture, because the PAIR is the claim.

    Split apart, each half passes against a build that gets the other wrong: an
    admitted-before case alone is satisfied by an exception that never expires,
    and a refused-after case alone by one that was never granted. Only the pair
    shows a transition that is genuinely non-renewable.

    The admitted leg is asserted on the NOTICE as well as on the admission. The
    clause requires an out-of-window carrier to be surfaced as an admitted
    transition and never silently described as in-window, so a build that simply
    returned `current` here would satisfy "the dispatch proceeded" while erasing
    the one fact an operator needs: that this engine is running on borrowed time
    and until when.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repo = _repo(tmp_path=tmp_path)
    _install(
        monkeypatch=monkeypatch,
        runner=_runner(releases=_carrier_releases(), ancestors=frozenset({_CARRIER_TAG})),
        now=_NOW,
    )
    journal_path = tmp_path / "journal.jsonl"

    admitted = _wall_exit(repo=repo, journal_path=journal_path)

    assert admitted is None
    notice = capsys.readouterr().err
    assert "bd-ib-6tcjfx" in notice
    assert _CARRIER_TAG in notice
    assert "2026-11-14T00:00:00+00:00" in notice
    assert "transition" in notice
    # DESCRIBED AS NOT IN-WINDOW, asserted POSITIVELY. The obvious probe —
    # `"in-window" not in notice` — is the wrong instrument: the notice's own
    # disclaimer contains that phrase, so the absence check fails on a notice
    # that says exactly the right thing. Presence of a phrase is not assertion
    # of it, and only reading the surrounding sentence tells the two apart.
    assert "NOT as an in-window base" in notice
    assert f"{CURRENCY_WINDOW_DAYS}-calendar-day window" in notice
    records = _records(journal_path=journal_path)
    assert [record["condition"] for record in records] == ["transition-admitted"]
    assert records[0]["blocking"] is False

    # The same carrier, the same observation, evaluated AT the deadline instant.
    _install(
        monkeypatch=monkeypatch,
        runner=_runner(releases=_carrier_releases(), ancestors=frozenset({_CARRIER_TAG})),
        now=_DEADLINE,
    )
    expired_journal = tmp_path / "expired-journal.jsonl"

    refused = _wall_exit(repo=repo, journal_path=expired_journal)

    assert refused == EXIT_PRECONDITION_ERROR
    refusal = capsys.readouterr().err
    assert CONDITION_OUT_OF_WINDOW in refusal
    # No compatibility hold and no notice can renew it: the expired leg says
    # nothing about a transition at all.
    assert "bd-ib-6tcjfx" not in refusal
    expired_records = _records(journal_path=expired_journal)
    assert [record["condition"] for record in expired_records] == [CONDITION_OUT_OF_WINDOW]


def test_scenario130_the_window_is_ordered_by_publication_time_not_version_or_enumeration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A prerelease published last IS the newest release, whatever its version says.

    The fixture is built so the three candidate orderings disagree and each
    produces a DIFFERENT VERDICT, which is the only shape that can fail for the
    right reason:

    - By publication time the newest release is the `v0.378.0-nightly.0`
      prerelease of 2026-10-10, the base is `v0.390.0` of 2026-09-05, and the gap
      is 35 calendar days — out of window, so the dispatch is REFUSED.
    - By the forge's own enumeration order, or by semantic version, the newest
      release is the stable `v0.400.0` of 2026-09-01, which the base POSTDATES —
      so the gap is negative, the window passes and the dispatch is ADMITTED.

    An admitted dispatch here is therefore not a near miss: it is a build reading
    a semantic version or a list position where `constraints.md` says publication
    time is the only ordering evidence. The refusal naming the nightly as the
    newest release is what says the right release class was compared.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repo = _repo(tmp_path=tmp_path)
    _install(
        monkeypatch=monkeypatch,
        runner=_runner(
            releases=_release_class_releases(),
            ancestors=frozenset({_RELEASE_CLASS_BASE_TAG}),
        ),
        now=_NOW,
    )
    journal_path = tmp_path / "journal.jsonl"

    exit_code = _wall_exit(repo=repo, journal_path=journal_path)

    assert exit_code == EXIT_PRECONDITION_ERROR
    refusal = capsys.readouterr().err
    assert CONDITION_OUT_OF_WINDOW in refusal
    assert "35 calendar days" in refusal
    # The PRERELEASE is named as the newest observed release, and the
    # higher-versioned stable release is not.
    assert (
        "  newest observed upstream release: v0.378.0-nightly.0"
        " published 2026-10-10T00:00:00+00:00"
    ) in refusal
    assert "  upstream base: v0.390.0 published 2026-09-05T00:00:00+00:00" in refusal
    records = _records(journal_path=journal_path)
    assert [record["condition"] for record in records] == [CONDITION_OUT_OF_WINDOW]
