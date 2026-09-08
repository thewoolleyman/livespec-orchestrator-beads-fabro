"""Integration-tier acceptance for the loop's bounded credential re-probe.

Binds `SPECIFICATION/scenarios.md` "Scenario 121 — A refused credential probe
re-probes on a cadence instead of exiting, and no clock gates it" and the two
clauses it realizes in `SPECIFICATION/contracts.md` section "Provider spend
containment": "The admission-time credential-probe refusal re-probes rather than
exiting" and "The probe refusal's remedy carries no timing claim as an
instruction".

The whole `loop` invocation runs as production code — the real
`dispatcher.main(argv=["loop", ...])` CLI, the real store/client seam against
the in-memory `FakeBeadsClient`, the real on-disk journal, the real
`.livespec.jsonc` cadence read, and the real `time.sleep` the wait calls. Only
the two seams that leave the process are stood in: the bounded Messages API
probe and the factory launch.

DRIVING THE WHOLE INVOCATION IS WHAT MAKES THE POSITIVE CASE MEAN ANYTHING. The
scenario's claim is that the loop "resumes normal admission on that first usable
result WITHOUT HAVING EXITED", and neither half of that is observable from the
wait alone: exiting and resuming are both things the invocation does after the
wait returns. So the assertion is that a run was created for the seeded item,
read off the recording launch stand-in — an exit code of 0 would be satisfied
just as well by a loop that admitted nothing.

THE CONTROL IS THE REFUSAL THE WAIT DOES NOT GOVERN. A `revoked` credential
runs the same invocation with the same fixture and must NOT wait: without it,
"the loop waited and then dispatched" is indistinguishable from a gate that
waits on every refusal, which would hang a misconfigured wrapper rather than
report it. The discriminator is the journal — refusal records present in one
leg, absent in the other — because both legs are otherwise identical.

THE CADENCE IS OBSERVED, NOT ASSUMED. The fixture commits
`credential_reprobe_interval_seconds: 1` and the wait sleeps for real, so the
elapsed time of the invocation is evidence the committed dial was the one read.
A stubbed sleep would prove only that some number reached some stand-in.
"""

from __future__ import annotations

import json
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_credentials, _dispatcher_loop
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    ClaudeProbeObservation,
    classify_claude_probe,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_reprobe import (
    CREDENTIAL_REPROBE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    dispatch_provider_exhaustion,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-reprobe"
_CADENCE_SECONDS = 1
_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"
_WORKFLOW_DIR = ".fabro/workflows/implement-work-item"

_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
)
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

# The provider-limit observation the incident produced: HTTP 429 carrying the
# rate-limit error type. Nothing here carries a reset instant, because the
# classifier is not given one to adopt.
_RATE_LIMITED = ClaudeProbeObservation(
    http_status=429, error_type="rate_limit_error", input_tokens=None, output_tokens=None
)
_REVOKED = ClaudeProbeObservation(
    http_status=401, error_type="authentication_error", input_tokens=None, output_tokens=None
)
_USABLE = ClaudeProbeObservation(http_status=200, error_type=None, input_tokens=8, output_tokens=1)


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment + a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("credential-reprobe")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:credential-reprobe")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands."
        "_dispatcher_sibling_clones.fetch_fleet_manifest_text",
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
    """One admission-eligible ready item carrying gradeable acceptance criteria."""
    item = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="A dispatchable slice",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="- The thing is done.\n",
    )
    append_work_item(path=_config(), item=item)
    return item


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                    "dispatcher": {
                        "wip_cap": 3,
                        "acceptance_mode": "ai-only",
                        "credential_reprobe_interval_seconds": _CADENCE_SECONDS,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    workflow = repo / _WORKFLOW_DIR
    workflow.mkdir(parents=True)
    _ = (workflow / "workflow.toml").write_text(_WORKFLOW_TOML, encoding="utf-8")
    _ = (workflow / "workflow.fabro").write_text(_GRAPH, encoding="utf-8")
    return repo


def _scripted_probe(*, observations: list[ClaudeProbeObservation]) -> Callable[..., object]:
    """The bounded Messages API probe, replaced by a scripted classification.

    The stand-in stops at the network boundary: each scripted OBSERVATION is
    still classified by the production `classify_claude_probe`, so the condition
    the wait reads is the one the real classifier assigns.
    """
    calls: list[int] = []

    def _probe(*, token: str) -> object:
        _ = token
        index = min(len(calls), len(observations) - 1)
        calls.append(index)
        return classify_claude_probe(observation=observations[index])

    return _probe


def _recording_run_dispatch(*, calls: list[str]) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in recording that a factory run WAS created."""

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        calls.append(plan.work_item_id)
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="dispatched",
        )

    return _run_dispatch


def _loop(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    observations: list[ClaudeProbeObservation],
) -> tuple[int, list[str]]:
    """Drive one real `loop` invocation; report its exit code and what it launched."""
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording_run_dispatch(calls=calls))
    monkeypatch.setattr(
        _dispatcher_credentials,
        "probe_claude_credential",
        _scripted_probe(observations=observations),
    )
    argv = ["loop", "--repo", str(repo), "--budget", "3", "--no-close-on-merge"]
    return main(argv=argv), calls


def _records(*, repo: Path) -> list[dict[str, object]]:
    """Every journal record the invocation appended.

    No absent-file guard: every `loop` invocation here reaches the preamble,
    which journals, so the file always exists by the time a case reads it.
    """
    path = repo / _JOURNAL
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_the_loop_reprobes_and_resumes_on_the_first_usable_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rate-limited probe waits on the committed cadence and then dispatches."""
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)

    started = time.monotonic()
    exit_code, calls = _loop(
        repo=repo, monkeypatch=monkeypatch, observations=[_RATE_LIMITED, _USABLE]
    )
    elapsed = time.monotonic() - started

    # The invocation did not exit on the refusal: it went on to admit the item
    # and create a run for it.
    assert (exit_code, calls) == (0, [_ITEM_ID])
    # Each refused probe is journaled as exactly one record.
    refused = [
        record for record in _records(repo=repo) if record["stage"] == CREDENTIAL_REPROBE_STAGE
    ]
    assert len(refused) == 1
    assert refused[0]["condition"] == "exhausted"
    assert refused[0]["http_status"] == 429
    assert refused[0]["reprobe_interval_seconds"] == _CADENCE_SECONDS
    # The committed cadence is what the wait actually slept.
    assert elapsed >= _CADENCE_SECONDS


def test_a_refusal_the_wait_does_not_govern_is_reported_rather_than_waited_on(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: a revoked credential must not be re-probed for ever.

    Same fixture, same invocation, one different probe classification. Without
    this leg the positive case above is equally consistent with a gate that
    waits on every refusal, which would turn a rotated-out token into a hang.
    """
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)

    exit_code, calls = _loop(repo=repo, monkeypatch=monkeypatch, observations=[_REVOKED])

    assert calls == []
    assert exit_code != 0
    refused = [
        record for record in _records(repo=repo) if record["stage"] == CREDENTIAL_REPROBE_STAGE
    ]
    assert refused == []


def test_a_usable_probe_does_not_retire_an_unexpired_exhaustion_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wait creates no fourth retirement route.

    The record is held across the whole invocation — the refusal, the wait, and
    the usable result that ends it — and admission stays refused BY THE RECORD,
    which is a different refusal from the one the wait governs.
    """
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path)
    journal_path = repo / _JOURNAL
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    _ = journal_path.write_text(
        json.dumps(
            {
                "at": "2026-09-08T00:00:00Z",
                "stage": "provider-exhaustion-observed",
                "work_item_id": "bd-ib-held",
                "provider": "anthropic",
                "governing_condition": "provider_usage_limit",
                "record_expires_at": "2099-01-01T00:00:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    _exit_code, calls = _loop(
        repo=repo, monkeypatch=monkeypatch, observations=[_RATE_LIMITED, _USABLE]
    )

    held = dispatch_provider_exhaustion(journal_path=journal_path, now_iso="2026-09-08T00:10:00Z")
    assert held is not None
    assert held.provider == "anthropic"
    stages = [record["stage"] for record in _records(repo=repo)]
    assert "provider-exhaustion-cleared" not in stages
    # The wait ran — so the usable result really did reach admission — and
    # admission was then refused BY THE RECORD. Reading both stages is what
    # separates "the record survived" from "nothing happened at all": an empty
    # launch list alone is consistent with either.
    assert CREDENTIAL_REPROBE_STAGE in stages
    assert "provider-exhaustion-refusal" in stages
    assert calls == []


def test_the_probe_refusal_remedy_carries_no_wait_until_clock_instruction() -> None:
    """No provider-stated reset instant is presented as an instruction.

    The remedy names this repository's own cadence dial instead, and says in
    terms that a provider timing claim is an unverified claim rather than an
    instruction — which is the sentence the incident's clock-gated resumers
    would have had to contradict.
    """
    status = classify_claude_probe(observation=_RATE_LIMITED)

    assert status.condition == "exhausted"
    assert "credential_reprobe_interval_seconds" in status.remedy
    assert "unverified provider claim" in status.remedy
    assert "never an instruction" in status.remedy
    assert "wait before retrying" not in status.remedy
