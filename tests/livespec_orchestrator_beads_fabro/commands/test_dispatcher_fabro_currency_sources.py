"""Tests for the gathering half of the Fabro currency predicate.

`test_dispatcher_fabro_currency.py` covers the RULE. This module covers what that
rule is handed: the two argvs, the serving-commit read off the target's own
server, the paginated releases parse and the bounded ancestry walk.

TWO CLAIMS HERE ARE READ OFF THE SEAM RATHER THAN OFF A RETURN VALUE, because no
return value can carry them. That the serving commit comes from the SERVER's
section and not the client's is a claim about which line was parsed, and the two
sections differ only in their label; and that the ancestry walk is BOUNDED is a
claim about how many forge calls were spent, which a correct-but-unbounded walk
would satisfy at every other assertion.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency import (
    FABRO_UPSTREAM_REPO,
    FabroRelease,
    FabroReleaseObservation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency_sources import (
    ObservationReading,
    compare_argv,
    fabro_currency_subject,
    parse_releases,
    releases_argv,
    resolved_base,
    serving_integration_commit,
)

_REPO = Path("/repo")
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_FABRO_BIN = "/home/ubuntu/.fabro/bin/fabro"
_SERVER_COMMIT = "8869e88"
_CLIENT_COMMIT = "4b8cc85"
_NOW = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)

# Every `gh api` flag that adds a parameter to the REQUEST BODY, and so flips
# the inferred method from GET to POST. Both spellings of each are listed
# because a one-character short form is exactly what an argv review skims past.
_GH_BODY_PARAMETER_FLAGS = ("-F", "--field", "-f", "--raw-field", "--input")

# Both spellings of the method flag, for the same reason.
_GH_METHOD_FLAGS = ("--method", "-X")

# `fabro version --json` exactly as the two hp servers printed it on 2026-10-11:
# the pinned 0.254 engine on :32276 and the Petri-era candidate on :32278, each
# read through a client of its own era. Captured, not composed, because the
# previous fixtures were composed: they invented a one-line `Server: (<sha> x)`
# form that no build prints, the parser was written to that form, and the gate
# refused every real dispatch while every test passed.
_CAPTURED_LEGACY_VERSION_JSON = """{
  "client": {
    "version": "0.254.0",
    "git_sha": "8869e88",
    "build_date": "2026-10-01",
    "profile": "release",
    "os": "linux",
    "arch": "x86_64"
  },
  "server": {
    "address": "https://hp-xubuntu.perch-rudd.ts.net:32276",
    "version": "0.254.0",
    "git_sha": "8869e88",
    "build_date": "2026-10-01",
    "profile": "release",
    "os": "linux",
    "arch": "x86_64",
    "uptime_secs": 811718
  }
}
"""
_CAPTURED_CANDIDATE_VERSION_JSON = """{
  "client": {
    "version": "0.382.0-nightly.0",
    "git_sha": "adeefec",
    "build_date": "2026-10-11",
    "profile": "release",
    "os": "linux",
    "arch": "x86_64"
  },
  "server": {
    "address": "https://hp-xubuntu.perch-rudd.ts.net:32278",
    "version": "0.378.0-nightly.0",
    "git_sha": "64b9d88",
    "build_date": "2026-10-06",
    "profile": "release",
    "os": "linux",
    "arch": "x86_64",
    "uptime_secs": 256741
  }
}
"""


@dataclass(kw_only=True)
class _Runner:
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


def _factory(*, server: str | None = _SERVER) -> FactoryTarget:
    return FactoryTarget(name="hp", server=server, dev_token=None, fabro_bin=_FABRO_BIN)


def _version_runner(*, stdout: str, exit_code: int = 0) -> _Runner:
    return _Runner(
        results={
            (_FABRO_BIN, "version", "--json"): CommandResult(
                exit_code=exit_code, stdout=stdout, stderr=""
            )
        }
    )


def _version_json(*, server_commit: str | None, client_commit: str = _CLIENT_COMMIT) -> str:
    """`fabro version --json`'s shape, with the server section optional."""
    payload: dict[str, object] = {"client": {"version": "0.254.0", "git_sha": client_commit}}
    if server_commit is not None:
        payload["server"] = {"address": _SERVER, "version": "0.254.0", "git_sha": server_commit}
    return json.dumps(payload)


def _declared_method(*, argv: list[str]) -> str | None:
    """The method `argv` declares explicitly, or `None` when it leaves it inferred."""
    for index, token in enumerate(argv[:-1]):
        if token in _GH_METHOD_FLAGS:
            return argv[index + 1]
    return None


def _resolves_as_a_get(*, argv: list[str]) -> bool:
    """Whether `gh` sends `argv` as a GET: declared so, or carrying no body."""
    if _declared_method(argv=argv) is not None:
        return _declared_method(argv=argv) == "GET"
    return not any(flag in argv for flag in _GH_BODY_PARAMETER_FLAGS)


def _release(*, tag: str, days_ago: int) -> FabroRelease:
    return FabroRelease(tag=tag, published_at=_NOW.replace(hour=0) - _days(days=days_ago))


def _days(*, days: int) -> object:
    from datetime import timedelta

    return timedelta(days=days)


def test_the_releases_argv_names_the_upstream_repository_and_projects_one_object_per_line() -> None:
    """The projection is what makes a PAGINATED answer parseable.

    Without `--jq`, `gh api --paginate` concatenates one array per page, so a
    single-document parse succeeds on a one-page answer and fails on every
    multi-page one — a reader that works until upstream grows.
    """
    argv = releases_argv()

    assert argv[:2] == ["gh", "api"]
    assert f"repos/{FABRO_UPSTREAM_REPO}/releases" in argv
    assert "--paginate" in argv
    assert argv[-1] == ".[] | {tag: .tag_name, published_at: .published_at}"


def test_every_forge_read_resolves_as_a_get_rather_than_as_a_write() -> None:
    """A read carrying a body parameter is dispatched by `gh` as a POST.

    `gh api`'s own help states the rule: "The default HTTP request method is
    `GET` normally and `POST` if any parameters were added." So an argv that
    MEANS a read while carrying `-F per_page=100` and declaring no method is
    sent to `POST /repos/fabro-sh/fabro/releases` -- the CREATE-A-RELEASE
    endpoint of a third-party repository -- with `{"per_page":100}` as its body.
    It cannot return releases, so the gather reports the surface as unobservable
    and the gate fails closed on every dispatch, while each attempt issues an
    unauthorized write against upstream.

    `gh` resolves a GET two ways and both are admissible: declare `--method GET`
    explicitly, or carry no body parameter at all. What is NOT admissible is
    body parameters with the method left to inference -- which is why this reads
    the relationship between the two rather than pinning one spelling.

    THE FIRST ASSERTION IS A CONTROL ON THE PREDICATE ITSELF, and it is the
    load-bearing one. `_resolves_as_a_get` over an argv set that happens to hold
    no body parameters passes whether or not the flag table is populated, so a
    gutted `_GH_BODY_PARAMETER_FLAGS` -- or a `_declared_method` that returns
    `None` for everything -- would report both reads conforming while seeing
    nothing. A deliberate WRITE is therefore classified first: that case can
    only pass while the predicate can still return the refusing verdict, which
    is the question a pair of passing reads cannot answer. The argv is the
    repository's own conforming write form, spelled as
    `_dispatcher_publish_branch_preserve.create_ref_argv` builds it.
    """
    deliberate_write = [
        "gh",
        "api",
        "--method",
        "POST",
        f"repos/{FABRO_UPSTREAM_REPO}/git/refs",
        "--raw-field",
        "ref=refs/heads/x",
    ]
    assert not _resolves_as_a_get(argv=deliberate_write)

    for name, argv in (
        ("releases", releases_argv()),
        ("compare", compare_argv(base="v0.254.0", head=_SERVER_COMMIT)),
    ):
        assert _resolves_as_a_get(argv=argv), (
            f"the {name} read carries body parameter flag(s)"
            f" {[flag for flag in _GH_BODY_PARAMETER_FLAGS if flag in argv]} and declares"
            f" method {_declared_method(argv=argv)!r}, so `gh` sends it as a POST"
        )


def test_the_compare_argv_names_the_upstream_repository_rather_than_gh_placeholders() -> None:
    """`{owner}`/`{repo}` would resolve against the GOVERNED tenant, not upstream."""
    argv = compare_argv(base="v0.254.0", head=_SERVER_COMMIT)

    assert argv[2] == f"repos/{FABRO_UPSTREAM_REPO}/compare/v0.254.0...{_SERVER_COMMIT}"
    assert "{owner}" not in argv[2]


def test_the_serving_commit_comes_from_the_server_section_and_not_the_client_section() -> None:
    """The discriminating case: the two sections report DIFFERENT commits.

    `fabro version` reports the client beside the server, and reading the client's
    commit would report the local client build as the engine a dispatch lands on,
    which is the fleet-global surrogate the clause forbids.
    """
    runner = _version_runner(stdout=_version_json(server_commit=_SERVER_COMMIT))

    commit = serving_integration_commit(
        factory=_factory(), fabro_bin=_FABRO_BIN, runner=runner, cwd=_REPO
    )

    assert commit == _SERVER_COMMIT


def test_the_version_read_addresses_the_targets_own_server_through_the_environment() -> None:
    """Read off the seam, because the argv cannot carry it.

    `fabro version` takes no per-subcommand `--server` on the pinned engine, so
    the port addresses the target through `FABRO_SERVER`; an unaddressed read
    returns whichever server the host's ambient configuration names.

    THE REST OF THAT DELTA IS A SCRUB, and it is covered by
    `test_fabro_currency_probe_credential_scrub.py` rather than here: a foreign
    Fabro home has to be PRESENT in the dispatching environment for the removal
    to be observable at all, and this case asserts only the binding.
    """
    captured: list[Mapping[str, str | None] | None] = []

    @dataclass(kw_only=True)
    class _EnvRunner:
        def run(
            self,
            *,
            argv: list[str],
            cwd: Path,
            timeout_seconds: float,
            env: Mapping[str, str | None] | None = None,
            stdin: int | None = None,
        ) -> CommandResult:
            del argv, cwd, timeout_seconds, stdin
            captured.append(env)
            return CommandResult(
                exit_code=0, stdout=_version_json(server_commit=_SERVER_COMMIT), stderr=""
            )

    _ = serving_integration_commit(
        factory=_factory(), fabro_bin=_FABRO_BIN, runner=_EnvRunner(), cwd=_REPO
    )

    assert [None if one is None else one.get("FABRO_SERVER") for one in captured] == [_SERVER]


def test_a_client_that_exits_non_zero_reports_no_serving_commit() -> None:
    """Unobserved, not absent: the two have the same remedy and both fail closed."""
    runner = _version_runner(stdout="", exit_code=127)

    assert (
        serving_integration_commit(
            factory=_factory(), fabro_bin=_FABRO_BIN, runner=runner, cwd=_REPO
        )
        is None
    )


def test_output_with_no_server_section_reports_no_serving_commit() -> None:
    runner = _version_runner(stdout=_version_json(server_commit=None))

    assert (
        serving_integration_commit(
            factory=_factory(), fabro_bin=_FABRO_BIN, runner=runner, cwd=_REPO
        )
        is None
    )


def test_the_serving_commit_is_read_from_both_captured_server_builds() -> None:
    """The pinned engine and the Petri-era candidate, as each actually prints it.

    Each capture's client and server differ on the candidate, so this also
    discriminates the server section from the client one on real output.
    """
    for stdout, expected in (
        (_CAPTURED_LEGACY_VERSION_JSON, "8869e88"),
        (_CAPTURED_CANDIDATE_VERSION_JSON, "64b9d88"),
    ):
        commit = serving_integration_commit(
            factory=_factory(),
            fabro_bin=_FABRO_BIN,
            runner=_version_runner(stdout=stdout),
            cwd=_REPO,
        )

        assert commit == expected


def test_the_version_read_asks_for_the_json_form() -> None:
    """The human form spreads the server's build over several labelled lines."""
    runner = _version_runner(stdout=_CAPTURED_LEGACY_VERSION_JSON)

    _ = serving_integration_commit(
        factory=_factory(), fabro_bin=_FABRO_BIN, runner=runner, cwd=_REPO
    )

    assert runner.calls == [(_FABRO_BIN, "version", "--json")]


def test_output_that_is_not_json_reports_no_serving_commit() -> None:
    runner = _version_runner(stdout="Server: https://hp\n Git SHA: 8869e88\n")

    assert (
        serving_integration_commit(
            factory=_factory(), fabro_bin=_FABRO_BIN, runner=runner, cwd=_REPO
        )
        is None
    )


def test_a_server_git_sha_that_is_not_a_commit_reports_none() -> None:
    """A build-date string in the commit field must not be reported as a commit."""
    runner = _version_runner(stdout=_version_json(server_commit="2026-10-01"))

    assert (
        serving_integration_commit(
            factory=_factory(), fabro_bin=_FABRO_BIN, runner=runner, cwd=_REPO
        )
        is None
    )


def test_releases_parse_reads_every_projected_line_in_arrival_order() -> None:
    stdout = (
        json.dumps({"tag": "v0.378.0-nightly.0", "published_at": "2026-10-10T01:00:00Z"})
        + "\n\n"
        + json.dumps({"tag": "v0.254.0", "published_at": "2026-07-30T12:00:00+00:00"})
        + "\n"
    )

    releases = parse_releases(stdout=stdout)

    assert releases is not None
    assert [release.tag for release in releases] == ["v0.378.0-nightly.0", "v0.254.0"]
    assert releases[0].published_at == datetime(2026, 10, 10, 1, 0, tzinfo=timezone.utc)


def test_a_line_that_is_not_a_projected_release_object_fails_the_whole_parse() -> None:
    """Fail the parse rather than return a SHORT list.

    A short list is how a genuinely-ancestral tag disappears and a current build
    gets refused for having no base — a refusal manufactured by the parser.
    """
    assert parse_releases(
        stdout='{"tag": "v1", "published_at": "2026-10-10T01:00:00Z"}\nnope\n'
    ) is (None)


def test_a_release_object_missing_either_field_fails_the_parse() -> None:
    assert parse_releases(stdout=json.dumps({"tag": "v1"}) + "\n") is None
    assert parse_releases(stdout=json.dumps({"published_at": "2026-10-10T01:00:00Z"}) + "\n") is (
        None
    )
    assert parse_releases(stdout=json.dumps(["v1"]) + "\n") is None
    assert parse_releases(stdout=json.dumps({"tag": 7, "published_at": "x"}) + "\n") is None


def test_a_naive_publication_instant_fails_the_parse() -> None:
    """An offset-less instant cannot be compared against anything here.

    Treating it as UTC would silently invent the one fact the window rests on.
    """
    assert parse_releases(
        stdout=json.dumps({"tag": "v1", "published_at": "2026-10-10"}) + "\n"
    ) is (None)


def test_the_resolved_base_is_the_first_ancestor_in_observation_order() -> None:
    """Newest-first order means the first ancestor IS the latest-published one."""
    newest = _release(tag="v0.378.0-nightly.0", days_ago=1)
    middle = _release(tag="v0.370.0", days_ago=20)
    oldest = _release(tag="v0.254.0", days_ago=90)
    runner = _Runner(
        results={
            tuple(compare_argv(base="v0.378.0-nightly.0", head=_SERVER_COMMIT)): CommandResult(
                exit_code=0, stdout="diverged\n", stderr=""
            ),
            tuple(compare_argv(base="v0.370.0", head=_SERVER_COMMIT)): CommandResult(
                exit_code=0, stdout="identical\n", stderr=""
            ),
        }
    )

    base = resolved_base(
        observation=FabroReleaseObservation(releases=(newest, middle, oldest), observed_at=_NOW),
        serving_commit=_SERVER_COMMIT,
        runner=runner,
        cwd=_REPO,
    )

    assert base == middle
    # The walk STOPPED at the hit: the third candidate was never compared.
    assert tuple(compare_argv(base="v0.254.0", head=_SERVER_COMMIT)) not in runner.calls


def test_a_failed_or_unrecognised_comparison_does_not_promote_a_tag_to_base() -> None:
    """The fail-open this excludes: an unreachable forge accepting any tag.

    Both arms answer "not an ancestor", so the walk runs on and ends in a refusal
    rather than in a base nothing verified.
    """
    unreadable = _release(tag="v0.378.0-nightly.0", days_ago=1)
    unknown_status = _release(tag="v0.370.0", days_ago=20)
    runner = _Runner(
        results={
            tuple(compare_argv(base="v0.370.0", head=_SERVER_COMMIT)): CommandResult(
                exit_code=0, stdout="sideways\n", stderr=""
            )
        }
    )

    base = resolved_base(
        observation=FabroReleaseObservation(
            releases=(unreadable, unknown_status), observed_at=_NOW
        ),
        serving_commit=_SERVER_COMMIT,
        runner=runner,
        cwd=_REPO,
    )

    assert base is None
    assert len(runner.calls) == 2


def test_the_ancestry_walk_is_bounded_by_the_observation_and_spends_no_more() -> None:
    """Read off the CALL COUNT, which is the only instrument that can see a bound.

    A walk that re-asked, looped, or paged beyond what it was given returns the
    same `None` here, so every other assertion in this module would pass against
    one. The bound is the OBSERVATION: one call per release it was handed, and
    not one more.
    """
    releases = tuple(_release(tag=f"v0.{index}.0", days_ago=index) for index in range(50))
    runner = _Runner(results={})

    base = resolved_base(
        observation=FabroReleaseObservation(releases=releases, observed_at=_NOW),
        serving_commit=_SERVER_COMMIT,
        runner=runner,
        cwd=_REPO,
    )

    assert base is None
    assert len(runner.calls) == len(releases)


def test_the_ancestry_walk_reaches_an_ancestor_published_long_before_the_newest() -> None:
    """A base can be FAR down the publication order, and must still be found.

    This is the shape the ratified 0.254 carrier exception requires, and the one
    a candidate cap silently converts into the WRONG refusal. Measured against
    the live forge on 2026-10-11: `v0.254.0` is `identical` to the carrier commit
    `497aaba6`, and sits at publication-order index 80 of the 147 releases
    `fabro-sh/fabro` has published -- so a walk that stops at the 40 newest
    cannot reach it.

    What makes that mis-cut expensive is not the miss but the DIAGNOSIS. The
    30-day rule exists to refuse a base that is OLD, which means the base has to
    be found before it can be judged; a cap that hides it reports
    `no-release-tag-ancestor` instead -- a different condition, with a different
    corrective route, about a population that excluded the answer. So the
    carrier the exception must ADMIT is refused, and refused for a reason that
    reads like an unidentifiable build.

    The ancestor here sits at index 44 of 60, past any cap below the observation
    size, and the assertion is the BASE rather than the call count: a walk that
    spent the calls but returned `None` is the failure being closed.
    """
    releases = tuple(_release(tag=f"v0.{index}.0", days_ago=index) for index in range(60))
    ancestor = releases[44]
    runner = _Runner(
        results={
            tuple(compare_argv(base=ancestor.tag, head=_SERVER_COMMIT)): CommandResult(
                exit_code=0, stdout="identical\n", stderr=""
            )
        }
    )

    base = resolved_base(
        observation=FabroReleaseObservation(releases=releases, observed_at=_NOW),
        serving_commit=_SERVER_COMMIT,
        runner=runner,
        cwd=_REPO,
    )

    assert base == ancestor


def test_the_subject_names_the_observation_fault_ahead_of_the_serving_build_one() -> None:
    """An absent observation is a SHARED fault; an unidentified build is a local one.

    Reporting the per-target fault while the shared one stands sends the operator
    to the wrong host.
    """
    runner = _version_runner(stdout="", exit_code=127)

    subject = fabro_currency_subject(
        factory=_factory(),
        fabro_bin=_FABRO_BIN,
        runner=runner,
        cwd=_REPO,
        reading=ObservationReading(observation=None, failure="the forge read failed"),
    )

    assert subject.serving_commit is None
    assert subject.base is None
    assert subject.unobservable_detail == "the forge read failed"


def test_an_unidentified_serving_build_names_the_server_it_asked() -> None:
    runner = _version_runner(stdout="", exit_code=127)

    subject = fabro_currency_subject(
        factory=_factory(),
        fabro_bin=_FABRO_BIN,
        runner=runner,
        cwd=_REPO,
        reading=ObservationReading(
            observation=FabroReleaseObservation(
                releases=(_release(tag="v0.378.0-nightly.0", days_ago=1),), observed_at=_NOW
            ),
            failure=None,
        ),
    )

    assert subject.unobservable_detail is not None
    assert _SERVER in subject.unobservable_detail
    assert "could not be identified" in subject.unobservable_detail


def test_a_commit_with_no_release_tag_ancestor_states_the_scope_that_was_searched() -> None:
    """The bound is NAMED in the refusal, not left implicit.

    An absence asserted over an unstated population is what turns a bounded search
    into a false impossibility.
    """
    runner = _Runner(
        results={
            (_FABRO_BIN, "version", "--json"): CommandResult(
                exit_code=0, stdout=_version_json(server_commit=_SERVER_COMMIT), stderr=""
            )
        }
    )

    releases = tuple(_release(tag=f"v0.{index}.0", days_ago=index + 1) for index in range(7))

    subject = fabro_currency_subject(
        factory=_factory(),
        fabro_bin=_FABRO_BIN,
        runner=runner,
        cwd=_REPO,
        reading=ObservationReading(
            observation=FabroReleaseObservation(releases=releases, observed_at=_NOW),
            failure=None,
        ),
    )

    assert subject.serving_commit == _SERVER_COMMIT
    assert subject.base is None
    assert subject.unobservable_detail is not None
    # The scope is the POPULATION ACTUALLY SEARCHED, so it is read off the
    # observation's own size rather than off a constant. A fixed number here
    # would keep passing after a cap silently narrowed what the walk examined --
    # which is the mis-cut that made this absence false in the first place.
    assert f"among the {len(releases)} " in subject.unobservable_detail
    assert "no published release-tag ancestor" in subject.unobservable_detail


def test_a_target_declaring_no_server_is_asked_without_a_server_environment() -> None:
    """The implicit `default` target: the port falls back to the ambient reading.

    The gate never evaluates such a target, but the read must still be total — and
    the unidentified detail has to name something rather than `None`.
    """
    runner = _version_runner(stdout="")

    subject = fabro_currency_subject(
        factory=_factory(server=None),
        fabro_bin=_FABRO_BIN,
        runner=runner,
        cwd=_REPO,
        reading=ObservationReading(
            observation=FabroReleaseObservation(releases=(), observed_at=_NOW), failure=None
        ),
    )

    assert subject.unobservable_detail is not None
    assert "the ambient server" in subject.unobservable_detail


def test_a_resolved_base_leaves_the_subject_with_no_unobservable_detail() -> None:
    newest = _release(tag="v0.378.0-nightly.0", days_ago=1)
    runner = _Runner(
        results={
            (_FABRO_BIN, "version", "--json"): CommandResult(
                exit_code=0, stdout=_version_json(server_commit=_SERVER_COMMIT), stderr=""
            ),
            tuple(compare_argv(base=newest.tag, head=_SERVER_COMMIT)): CommandResult(
                exit_code=0, stdout="ahead\n", stderr=""
            ),
        }
    )

    subject = fabro_currency_subject(
        factory=_factory(),
        fabro_bin=_FABRO_BIN,
        runner=runner,
        cwd=_REPO,
        reading=ObservationReading(
            observation=FabroReleaseObservation(releases=(newest,), observed_at=_NOW),
            failure=None,
        ),
    )

    assert subject.base == newest
    assert subject.unobservable_detail is None


def test_a_populated_but_failed_reading_resolves_no_base_and_spends_no_comparison() -> None:
    """A STALE record is handed back populated, so the walk would succeed on it.

    Read off the CALL COUNT as well as the base, because "no base was resolved"
    and "no ancestry was asked" are different claims: a walk that ran and found
    nothing would satisfy the first while still having treated the expired record
    as a candidate set.
    """
    newest = _release(tag="v0.378.0-nightly.0", days_ago=10)
    runner = _Runner(
        results={
            (_FABRO_BIN, "version", "--json"): CommandResult(
                exit_code=0, stdout=_version_json(server_commit=_SERVER_COMMIT), stderr=""
            ),
            tuple(compare_argv(base=newest.tag, head=_SERVER_COMMIT)): CommandResult(
                exit_code=0, stdout="ahead\n", stderr=""
            ),
        }
    )

    subject = fabro_currency_subject(
        factory=_factory(),
        fabro_bin=_FABRO_BIN,
        runner=runner,
        cwd=_REPO,
        reading=ObservationReading(
            observation=FabroReleaseObservation(releases=(newest,), observed_at=_NOW),
            failure="the cached observation is 9 calendar days old",
        ),
    )

    assert subject.base is None
    assert subject.observation is not None
    assert subject.observation_failure == "the cached observation is 9 calendar days old"
    assert tuple(compare_argv(base=newest.tag, head=_SERVER_COMMIT)) not in runner.calls
