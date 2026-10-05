"""The claim boundary of the host Codex credential decision (`bd-ib-tyqklx`).

The pre-claim gate grades the credential BEFORE `admit_and_select` moves the row
`ready -> active`, and the run-configuration overlay grades it AGAIN after the
claim, renewing nothing. That second grade is the point of exposure this module
exists to pin: between the two reads the clock advances and the host file can
change, so a credential the gate admitted can be below the floor by the time the
overlay reads it — and a refusal there happens with the row already claimed.

WHY AN END-TO-END CONTROL AND NOT A UNIT ONE. Every claim here is about the
COMPOSITION of four mechanisms that each already worked in isolation: the gate's
grade, the admission write, the overlay's grade, and
`release_pre_run_claim_if_needed`. Asserting any one of them cannot distinguish
"the window is closed" from "the window is open and nothing looks at it", because
both produce a non-zero exit and an unwritten overlay. So every case drives the
REAL `dispatcher.main(argv=["dispatch", ...])` and `["loop", ...]` entry points
over the real store seam and a real on-disk journal, and reads the answer off the
LEDGER ROW plus the launch seam.

TWO FAILURE MODES, each with its own case, and they are not one case twice.

The CLOCK case is the narrow-window one: the bounded renewal produces a
credential at the floor plus one second, the gate admits it, two seconds pass
while the item is claimed, and the overlay sees the floor minus one. It is
engineered to land inside the window rather than near it — a credential merely
"a bit stale" would refuse at the gate and never reach the claim at all, proving
nothing about this boundary. Measured here: the release valve already covered it,
so this case pins behaviour rather than repairing it.

The CHANGED-SOURCE case is the one that was genuinely broken. A host `auth.json`
rewritten between the two reads made the overlay's grade RAISE
(`json.JSONDecodeError` / `ValueError`) rather than refuse, and a bug-class escape
from inside `dispatch_one` skips `release_pre_run_claim_if_needed` entirely — so
the row stayed `active` with no run behind it, which is the exact stranded shape
the pre-claim position was adopted to retire. Measured 2026-10-05 against three
source shapes: malformed JSON, a credential carrying no `access_token`, and one
whose access token is not a JWT. That is why each case asserts the ledger row and
not merely the exit code: the broken build and the repaired one differ in the row,
never in the code.

TWO POSITIVE CONTROLS CARRY BOTH, because each refusing assertion is about
something NOT happening and so has a way of passing vacuously. A credential fresh
at both positions must LAUNCH, which is what makes `launched == []` elsewhere a
measurement rather than a property of a seam that can never record. And
`_drive`'s raise-capture is shown to report a raise when one happens, because on
a repaired build nothing raises and `raised == []` would otherwise be
indistinguishable from a catcher that is unreachable or names the wrong class.

NO CASE MAY SPEND A SECOND RENEWAL. The renewal count is read off one recorder
spanning the whole invocation, because "the gate owns the one bounded renewal" is
a property of the dispatch as a whole rather than of either surface — and the
launching control is what shows the count is not an artifact of refusing.
"""

from __future__ import annotations

import base64
import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_codex_credential_gate,
    _dispatcher_credentials,
    _dispatcher_loop,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_early_renewal import (
    CodexRenewalOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_projection import (
    CODEX_FRESHNESS_RUN_BUDGET_SECONDS,
    codex_freshness_required_seconds,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-claimbound"

# The code a dispatch that FAILED reports, as distinct from the precondition
# code 3 every PRE-claim wall reports. Both cases here assert this one, and
# the distinction is itself a discriminator: a build whose refusal happened at
# the gate instead of at the overlay would exit 3, so an assertion of merely
# "non-zero" would pass for a run that never reached the position under test.
_EXIT_DISPATCH_FAILED = 1

# The floor the dispatch freshness gate enforces, read off the PRODUCTION
# derivation rather than written here: a literal would keep agreeing with itself
# after the budget child moves the requirement, and both cases below are
# positioned relative to this number by one second.
_REQUIRED = codex_freshness_required_seconds(run_budget_seconds=CODEX_FRESHNESS_RUN_BUDGET_SECONDS)

_NOW = 1_700_000_000

# How far the clock advances between the gate's grade and the overlay's. Two
# seconds is deliberately tiny: the window this pins is the one an operator
# cannot avoid, not a long queue wait.
_CLAIM_ELAPSED = 2

_HOST_REFRESH_TOKEN = "host-refresh-token"

_WRAPPER = ["/usr/local/bin/with-livespec-env.sh", "--"]
_FLEET_MANIFEST_TEXT = (
    '{\n  "owner": "thewoolleyman",\n  "members": [{ "repo": "livespec", "class": "core" }]\n}\n'
)
_RESERVED_DIR = ".fabro/workflows/implement-work-item"
_WORKFLOW_TOML = '[workflow]\ngraph = "workflow.fabro"\n\n[run.environment]\nid = "fabro-sandbox"\n'
_GRAPH = (
    "digraph ImplementWorkItem {\n"
    "    graph [\n"
    '        stall_timeout="7200s"\n'
    "    ]\n"
    "\n"
    "    implement [\n"
    '        timeout="1800s"\n'
    "    ]\n"
    "}\n"
)


@pytest.fixture(autouse=True)
def _dispatch_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup."
        "github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:codex-credential-claim-boundary")
    for topic in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(topic, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones."
        "fetch_fleet_manifest_text",
        lambda: _FLEET_MANIFEST_TEXT,
    )
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _seed_item() -> WorkItem:
    """One dispatchable item whose criteria parse, so the criteria wall clears.

    The credential gate sits after that wall, so an item with nothing gradeable
    would be refused for the wrong reason and both cases here would pass against
    a boundary that was never exercised.
    """
    item = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="Exercise the Codex credential claim boundary",
        description=(
            "## Definition of Done\n"
            "\n"
            "- The dispatch refuses before claiming when the credential cannot be renewed.\n"
            "\n"
            "References: ## Worker credential projection\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria=(
            "- The dispatch refuses before claiming when the credential cannot be renewed."
        ),
    )
    append_work_item(path=_config(), item=item)
    return item


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "credential_wrapper": _WRAPPER,
                "git_author": {
                    "operator_name": "Chad Woolley",
                    "operator_email": "thewoolleyman@gmail.com",
                },
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {"wip_cap": 3, "acceptance_mode": "ai-only"},
                },
            }
        ),
        encoding="utf-8",
    )
    workflow = repo / _RESERVED_DIR
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    return repo


def _auth_json_with_exp(*, exp: int) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": f"header.{payload}.sig",
                "refresh_token": _HOST_REFRESH_TOKEN,
                "id_token": "id-token-value",
                "account_id": "acct-123",
            },
        }
    )


def _arm_credential_window(
    *,
    monkeypatch: pytest.MonkeyPatch,
    post_renewal_source: str,
    post_claim_source: str,
    renewals: list[str],
) -> None:
    """Arm the window with THREE distinct reads, one per position that reads.

    The read sequence is what makes this a BOUNDARY control rather than a gate
    test, and getting it wrong is how the first draft of this module passed for
    the wrong reason: feeding the changed source to the gate's own post-renewal
    re-read made the GATE refuse, before any claim existed, so the post-claim
    position was never reached and the three changed-source cases were measuring
    a surface they do not name.

    - read 1 — the gate, pre-renewal. BELOW the floor, so the bounded renewal is
      reached at all.
    - read 2 — the gate, post-renewal. `post_renewal_source`. This one MUST
      admit, because everything asserted here happens after the claim.
    - read 3 and later — the overlay, post-claim. `post_claim_source`.

    The GATE's clock is held at `_NOW` for both of its readings and the OVERLAY's
    clock is advanced by `_CLAIM_ELAPSED`, modelling exactly the interval this
    module is about: the time the admission write and the claim take. The two
    clocks are separate seams in production (the gate resolves
    `wall_clock_epoch`, the overlay reads `time.time`), so holding one and moving
    the other is the real shape rather than a contrivance.
    """
    reads = [_auth_json_with_exp(exp=_NOW - 10), post_renewal_source]

    def _read() -> str:
        return reads.pop(0) if reads else post_claim_source

    def _renew() -> CodexRenewalOutcome:
        renewals.append("requested")
        return CodexRenewalOutcome(
            answered=True, detail="the renewal request was answered by the host Codex app-server"
        )

    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", _read)
    monkeypatch.setattr(_dispatcher_codex_auth, "renew_host_codex_credential", _renew)
    monkeypatch.setattr(_dispatcher_codex_credential_gate, "wall_clock_epoch", lambda: _NOW)
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: _NOW + _CLAIM_ELAPSED)


def _recording_run_dispatch(*, launched: list[str]) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in recording that a factory run WAS created."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        launched.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="dispatched",
        )

    return _run_dispatch


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _row() -> WorkItem:
    rows = read_work_items(path=_config())
    return next(row for row in rows if row.id == _ITEM_ID)


def _drive(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    subcommand: str,
) -> tuple[int, list[str], list[str]]:
    """Drive ONE real dispatch; report its code, what launched, and what raised.

    A raised exception is CAPTURED rather than allowed to propagate because it is
    one of the outcomes under test: a credential-decode fault escaping
    `dispatch_one` as a bug skips the claim-release valve, and the assertion that
    distinguishes the repaired build from the broken one is `raised == []`.
    """
    launched: list[str] = []
    raised: list[str] = []
    monkeypatch.setattr(
        _dispatcher_loop, "run_dispatch", _recording_run_dispatch(launched=launched)
    )
    argv = [subcommand, "--repo", str(repo), "--item", _ITEM_ID, "--no-close-on-merge"]
    if subcommand == "loop":
        argv += ["--budget", "3"]
    try:
        exit_code = main(argv=argv)
    except (ValueError, json.JSONDecodeError) as exc:
        raised.append(type(exc).__name__)
        exit_code = -1
    return exit_code, launched, raised


def test_a_credential_fresh_at_both_positions_launches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The POSITIVE control for every refusing case in this module.

    Without it, `launched == []` elsewhere is equally consistent with a harness
    whose launch seam can never record anything — an instrument that cannot
    return a hit, reporting no hits. This case is the same fixture, the same
    three reads and the same two clocks, differing only in that the credential
    outlives the floor at BOTH positions; it must reach the launch seam.

    It also demonstrates that the ordinary dispatch still spends exactly one
    bounded renewal, so the refusing cases' renewal counts are not an artifact
    of their refusing.
    """
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)
    renewals: list[str] = []
    comfortably_fresh = _auth_json_with_exp(exp=_NOW + _REQUIRED + 10_000)
    _arm_credential_window(
        monkeypatch=monkeypatch,
        post_renewal_source=comfortably_fresh,
        post_claim_source=comfortably_fresh,
        renewals=renewals,
    )

    exit_code, launched, raised = _drive(repo=repo, monkeypatch=monkeypatch, subcommand="dispatch")

    assert raised == []
    assert (exit_code, launched) == (0, [_ITEM_ID])
    assert renewals == ["requested"]


def test_the_raise_capture_reports_a_raise_when_one_happens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for `_drive`'s own catcher: it CAN return a hit.

    `raised == []` is the load-bearing assertion of the changed-source cases, and
    on a repaired build nothing raises — so without this case that assertion is
    indistinguishable from one whose catcher is unreachable or mis-typed. Here
    the entry point is stood in with a raiser of the exact class the catcher
    names, and the capture must report it.
    """
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)

    def _raising_main(**_kwargs: object) -> int:
        raise ValueError("credential decode escaped as a bug")

    monkeypatch.setattr(sys.modules[__name__], "main", _raising_main)

    exit_code, launched, raised = _drive(repo=repo, monkeypatch=monkeypatch, subcommand="dispatch")

    assert raised == ["ValueError"]
    assert (exit_code, launched) == (-1, [])


@pytest.mark.parametrize("subcommand", ["dispatch", "loop"])
def test_a_credential_that_ages_past_the_floor_during_the_claim_leaves_no_active_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, subcommand: str
) -> None:
    """The clock window: the overlay refuses and the claim is handed back.

    The credential is at the floor PLUS ONE at the gate's post-renewal grade, so
    the gate admits and the item is claimed; two seconds later the overlay grades
    the same credential at the floor MINUS ONE and refuses. The ledger row must
    be back at `ready` with no assignee, because an `active` row with no run is
    the stranded shape this whole position exists to retire.

    Both entry points are driven, since they reach `dispatch_one` through
    separate call sites.
    """
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)
    renewals: list[str] = []
    at_floor_plus_one = _auth_json_with_exp(exp=_NOW + _REQUIRED + 1)
    _arm_credential_window(
        monkeypatch=monkeypatch,
        post_renewal_source=at_floor_plus_one,
        # The SAME bytes the gate admitted. Nothing about the credential
        # changed; only the clock moved, which is what isolates this case to the
        # ageing window rather than to a rewritten file.
        post_claim_source=at_floor_plus_one,
        renewals=renewals,
    )

    exit_code, launched, raised = _drive(repo=repo, monkeypatch=monkeypatch, subcommand=subcommand)

    assert raised == []
    assert exit_code == _EXIT_DISPATCH_FAILED
    # No factory run was created, so there is nothing to reap.
    assert launched == []
    # The claim was handed back: `ready`, assignee cleared.
    row = _row()
    assert (row.status, row.assignee) == ("ready", None)
    # And the hand-back is on the record, naming the stage that refused.
    releases = [
        record
        for record in _journal_records(repo=repo)
        if record.get("stage") == "ledger-admit-release"
    ]
    assert [record["outcome_stage"] for record in releases] == ["run-config-overlay"]
    assert [record["status"] for record in releases] == ["ready"]
    # Exactly ONE bounded renewal across the whole invocation: the gate's.
    assert renewals == ["requested"]


@pytest.mark.parametrize(
    "post_claim_source",
    [
        "{not json",
        '{"auth_mode":"chatgpt","tokens":{"refresh_token":"r"}}',
        '{"auth_mode":"chatgpt","tokens":{"access_token":"not-a-jwt"}}',
    ],
    ids=["malformed-json", "no-access-token", "token-is-not-a-jwt"],
)
def test_a_source_that_changes_between_the_two_reads_refuses_without_stranding_the_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, post_claim_source: str
) -> None:
    """A rewritten host credential is a REFUSAL, never an escaping bug.

    All three shapes made the post-claim grade raise, and a raise from inside
    `dispatch_one` skips `release_pre_run_claim_if_needed` — so the row stayed
    `active` with no run. The three are parametrized rather than folded into one
    because they fail at three different depths of the decode (the JSON parse, the
    token lookup, the JWT split) and a guard catching only the first would leave
    the other two escaping exactly as before.

    `raised == []` is the load-bearing assertion. The exit code cannot carry this
    claim: the repaired build and the broken one both fail the dispatch, and they
    differ only in whether the claim came back.
    """
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)
    renewals: list[str] = []
    _arm_credential_window(
        monkeypatch=monkeypatch,
        # Comfortably fresh at BOTH clocks, so the gate admits and the overlay
        # would admit too had the file not changed. That is what makes the
        # rewritten bytes the only reason this dispatch refuses.
        post_renewal_source=_auth_json_with_exp(exp=_NOW + _REQUIRED + 10_000),
        post_claim_source=post_claim_source,
        renewals=renewals,
    )

    exit_code, launched, raised = _drive(repo=repo, monkeypatch=monkeypatch, subcommand="dispatch")

    # The fault is reported as a refusal, not as an escaping bug.
    assert raised == []
    assert exit_code == _EXIT_DISPATCH_FAILED
    assert launched == []
    row = _row()
    assert (row.status, row.assignee) == ("ready", None)
    # The diagnostic must say the credential could not be READ, and must claim
    # NEITHER a short lifetime nor an authentication failure: this path measured
    # neither, and an unparseable file supports neither conclusion.
    #
    # The detail is nested under the outcome record rather than sitting at the
    # top level, and reading the wrong key here would yield an empty string --
    # which would satisfy both absence assertions while proving nothing. Hence
    # the stage filter plus a non-empty check before the absences are read.
    detail = next(
        str(record["outcome"]["detail"])  # pyright: ignore[reportIndexIssue]
        for record in _journal_records(repo=repo)
        if record.get("stage") == "outcome"
    )
    assert "could not be parsed" in detail
    assert "seconds of usable lifetime" not in detail
    assert "authentication has failed" not in detail
    # A renewal cannot repair an unparseable credential, so the gate spent its
    # one request and nothing spent a second.
    assert renewals == ["requested"]
