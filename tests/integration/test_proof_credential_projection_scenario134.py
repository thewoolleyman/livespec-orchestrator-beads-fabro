"""A declared proof credential is projected by name, and four declarations are refused.

Binds `SPECIFICATION/scenarios.md` Scenario 134 and the
`SPECIFICATION/contracts.md` clause it realizes (ratified v114): a governed
repository MAY declare `dispatcher.proof_credentials` so its proof stages can
exercise the deliverable's backing services from inside the sandbox, and the
Dispatcher projects a declared credential through the SAME run-configuration
overlay channel that already carries the dispatch credential set — refusing
before any run exists when the declared name is withheld, when its value is
absent, when the declaration carries a credential-shaped value, or when its
capability is outside the closed enumeration.

THE PROJECTION IS READ OFF THE REAL CHANNEL, not off the builder. The positive
case drives the production `materialize_overlay` and reads the declared name out
of the overlay FILE it writes, in the same env table as the dispatch credential
set, because the claim is that the sandbox environment carries that name — and a
builder asserted in isolation would pass just as well while nothing threaded it
into the overlay. Its control is the same repository with the declaration
removed, which is what makes the name's presence evidence rather than a property
of every overlay.

THE REFUSALS ARE READ OFF THE REAL CLI. Each of the four drives
`dispatcher.main(argv=["dispatch", ...])` over a seeded tenant with the launch
seam recording, so "before any run exists" is observed on the seam itself rather
than inferred from an exit code — a dispatch can exit non-zero having already
created a run. Every refusing case also asserts the journal carries NO
`proof-credential` record: nothing was projected, and a journal saying otherwise
would describe a credential reaching a sandbox that never launched.

THE POSITIVE CLI CASE IS THE CONTROL FOR ALL FOUR. Without it, four refusals are
equally consistent with a gate that refuses every declaration, and the
discriminator has to be a repository whose declaration is admitted and whose
record is written.
"""

from __future__ import annotations

import base64
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_loop,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import materialize_overlay
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credentials import (
    COPIED_PROVISIONING,
    MINTED_PROVISIONING,
    PROOF_CREDENTIAL_JOURNAL_STAGE,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import main
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-proofcred"
_EXIT_PRECONDITION_ERROR = 3

# The declared credential, and the value the wrapper is pretending to inject. The
# name is deliberately free of every credential marker the declaration scan reads,
# because a name carrying one is itself a refusal case below.
_DECLARED_NAME = "ACME_STATUS_READER"
_DECLARED_VALUE = "acme-observer-value"
_READ_ONLY_DECLARATION = {
    "name": _DECLARED_NAME,
    "purpose": "observe the published build status of the deliverable",
    "capability": "read_only",
}

# The second declaration of the same repository: one whose provider DOES expose a
# management interface, so the Dispatcher mints it per run and revokes it when the
# run ends. The host holds a value under the same spelling, which must NOT be what
# reaches the sandbox — that is the whole difference minting makes.
_MANAGED_NAME = "ACME_MINTED_READER"
_MANAGED_HOST_VALUE = "acme-host-held-value"
_MANAGED_DECLARATION = {
    "name": _MANAGED_NAME,
    "purpose": "observe the published deployment state of the deliverable",
    "capability": "read_only",
}

# The journal stage the revoke leg records under, spelled as a literal rather
# than imported: the lease module does not exist at the Red of this slice, and a
# top-level import of it would make that Red a collection error instead of a
# genuine assertion failure.
_REVOKE_JOURNAL_STAGE = "proof-credential-revoke"

# A HERMETIC PROVIDER DOUBLE. It stands in for a provider's credential-management
# interface and nothing else: it appends one line per call to a ledger whose path
# it is handed on argv, and on `mint` it prints the value it minted on stdout —
# which is the whole contract the Dispatcher relies on. It reads the name, the
# declared capability and the per-run SCOPE out of the environment, exactly as a
# real management command would, so a build that addressed the two legs any other
# way would fail here rather than silently work on this double alone.
_PROVIDER_DOUBLE = '''\
"""A hermetic stand-in for one provider's credential-management interface."""

import os
import pathlib
import sys

_, ledger, operation = sys.argv
name = os.environ["LIVESPEC_PROOF_CREDENTIAL_NAME"]
capability = os.environ["LIVESPEC_PROOF_CREDENTIAL_CAPABILITY"]
scope = os.environ["LIVESPEC_PROOF_CREDENTIAL_SCOPE"]
with pathlib.Path(ledger).open("a", encoding="utf-8") as handle:
    _ = handle.write(f"{operation} {name} {capability} {scope}\\n")
if operation == "mint":
    _ = sys.stdout.write(f"acme-minted-{scope}\\n")
'''

# The same double's REFUSING twin: it writes nothing to any ledger and exits
# non-zero, which is how a provider whose management API is unreachable or out of
# quota presents. Writing nothing is the point — an empty ledger is what shows the
# refusal landed before anything was minted, so nothing is left needing a revoke.
_PROVIDER_DOUBLE_REFUSING = '''\
"""A hermetic stand-in for a provider management interface that cannot mint."""

import sys

_ = sys.stderr.write("acme-admin: quota exhausted\\n")
raise SystemExit(9)
'''

_WRAPPER = ["/usr/local/bin/with-acme-env.sh", "--"]
_FLEET_MANIFEST_TEXT = (
    '{"owner": "thewoolleyman", "members": [{"repo": "repo", "class": "impl-plugin"}]}'
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

# The four refusing declarations, each named by the fault it carries and paired
# with the substrings its refusal must name. Scenario 134 requires the declaration
# to be named in every case, the POSITION in the credential-shaped case, and the
# CAPABILITY in the over-scoped one.
_REFUSED_DECLARATIONS: dict[str, tuple[dict[str, str], tuple[str, ...]]] = {
    "withheld": (
        {
            "name": "BEADS_DOLT_PASSWORD",
            "purpose": "observe the work-items store from the proof stage",
            "capability": "read_only",
        },
        ("BEADS_DOLT_PASSWORD", "withheld"),
    ),
    "credential-shaped": (
        {
            "name": _DECLARED_NAME,
            "purpose": "observe build status using secret sk-acme-not-a-real-value",
            "capability": "read_only",
        },
        (_DECLARED_NAME, "purpose", "secret"),
    ),
    "over-scoped": (
        {
            "name": "ACME_DEPLOY_RUNNER",
            "purpose": "run the deploy smoke suite on the host substrate",
            "capability": "host_execute",
        },
        ("ACME_DEPLOY_RUNNER", "host_execute", "read_only"),
    ),
}


@pytest.fixture(autouse=True)
def _hermetic_dispatch_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> object:
    """Hermetic dispatch environment + a fresh in-memory tenant per case."""
    scratch = tmp_path_factory.mktemp("proof-credential-projection")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(scratch))
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-oauth-token")
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_loop.selfup.github_token_supplier",
        lambda: (lambda: "test-github-token"),
    )
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.setenv("LIVESPEC_INVOKER", "session:proof-credential-projection")
    for _ntfy_env in ("CLAUDE_NTFY_DISPATCHER_TOPIC", "CLAUDE_NTFY_TOPIC", "CLAUDE_NTFY_SERVER"):
        monkeypatch.delenv(_ntfy_env, raising=False)
    # The declared name must be ABSENT unless a case injects it, so the
    # absent-value refusal is reached by the environment the Dispatcher really
    # reads rather than by one the test only describes.
    monkeypatch.delenv(_DECLARED_NAME, raising=False)
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
    """One dispatchable item whose criteria parse, so the criteria wall clears.

    The proof-credential gate sits beside that wall and after it, so an item with
    nothing gradeable would be refused for the wrong reason and every case here
    would pass against a gate that was never wired at all.
    """
    item = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="Exercise a declared proof credential",
        description=(
            "## Definition of Done\n"
            "\n"
            "- The declared proof credential reaches the sandbox by name.\n"
            "\n"
            "References: ## Proof credential projection\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-01T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
        acceptance_criteria="- The declared proof credential reaches the sandbox by name.",
    )
    append_work_item(path=_config(), item=item)
    return item


def _provider_double(*, tmp_path: Path) -> tuple[Path, dict[str, object]]:
    """The hermetic double on disk, plus the management declaration driving it.

    Returns its LEDGER path beside the declaration, because every claim this
    module makes about minting and revoking is read off that ledger: it is the
    only place the provider's own view of the run is recorded.
    """
    script = tmp_path / "acme_admin_double.py"
    _ = script.write_text(_PROVIDER_DOUBLE, encoding="utf-8")
    ledger = tmp_path / "acme-admin-ledger.txt"
    return ledger, {
        _MANAGED_NAME: {
            "mint": [sys.executable, str(script), str(ledger), "mint"],
            "revoke": [sys.executable, str(script), str(ledger), "revoke"],
        }
    }


def _refusing_provider_double(*, tmp_path: Path) -> tuple[Path, dict[str, object]]:
    """The double's refusing twin on disk, plus the declaration driving it."""
    script = tmp_path / "acme_admin_refusing_double.py"
    _ = script.write_text(_PROVIDER_DOUBLE_REFUSING, encoding="utf-8")
    return tmp_path / "acme-admin-refusing-ledger.txt", {
        _MANAGED_NAME: {
            "mint": [sys.executable, str(script)],
            "revoke": [sys.executable, str(script)],
        }
    }


def _provider_ledger(*, ledger: Path) -> list[str]:
    """Every line the double wrote, or the empty list when it never ran.

    Tolerant of absence ON PURPOSE: "the double never ran" is the observation the
    minted cases are discriminating against, and it must read as an empty ledger
    rather than as an error about a missing file.
    """
    if not ledger.is_file():
        return []
    return ledger.read_text(encoding="utf-8").splitlines()


def _repo(
    *,
    tmp_path: Path,
    declared: list[dict[str, str]] | None,
    managed: dict[str, object] | None = None,
) -> Path:
    """A governed target whose committed configuration declares `proof_credentials`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    dispatcher: dict[str, object] = {"wip_cap": 3, "acceptance_mode": "ai-only"}
    if declared is not None:
        dispatcher["proof_credentials"] = declared
    if managed is not None:
        dispatcher["proof_credential_management"] = managed
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
                    "dispatcher": dispatcher,
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


def _dispatch(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    subcommand: str = "dispatch",
) -> tuple[int, list[str]]:
    """Drive one real dispatch and report its exit code plus what it launched."""
    calls: list[str] = []
    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _recording_run_dispatch(calls=calls))
    argv = [subcommand, "--repo", str(repo), "--item", _ITEM_ID, "--no-close-on-merge"]
    if subcommand == "loop":
        argv += ["--budget", "3"]
    return main(argv=argv), calls


def _journal_records(*, repo: Path) -> list[dict[str, object]]:
    """Every record this dispatch journaled.

    Read with no missing-file tolerance on purpose. Every case here drives a real
    dispatch, so the journal exists in all of them; a guard returning the empty
    list would turn "the dispatch never got far enough to journal anything" into
    the same observation as "it journaled no credential record", which is the
    distinction the refusing cases are asserting.
    """
    path = repo / "tmp" / "fabro-dispatch-journal.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _credential_records(*, repo: Path) -> list[dict[str, object]]:
    return [
        record
        for record in _journal_records(repo=repo)
        if record.get("stage") == PROOF_CREDENTIAL_JOURNAL_STAGE
    ]


# A fresh host Codex credential, so `materialize_overlay` reaches the projection
# instead of refusing at the freshness gate. Far-future `exp` rather than a
# patched clock, because what this module measures is downstream of that gate and
# a stale credential would refuse before any proof-credential line is rendered.
_FAR_FUTURE_EPOCH = 4_000_000_000


def _fresh_host_codex_auth() -> str:
    """A fake host `auth.json` whose access-token JWT expires far in the future."""
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": _FAR_FUTURE_EPOCH}).encode())
        .decode()
        .rstrip("=")
    )
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": f"header.{payload}.sig",
                "refresh_token": "host-refresh-token",
                "id_token": "id-token-value",
                "account_id": "acct-134",
            },
        }
    )


def _stand_in_host_codex_credential(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the projection at a fresh fake host credential and a fixed clock."""
    monkeypatch.setattr(_dispatcher_codex_auth, "read_host_codex_auth", _fresh_host_codex_auth)
    monkeypatch.setattr(_dispatcher_credentials.time, "time", lambda: 1_700_000_000)


def test_a_declared_read_only_credential_is_admitted_and_journaled_by_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive control: the dispatch proceeds and one record names the declaration."""
    monkeypatch.setenv(_DECLARED_NAME, _DECLARED_VALUE)
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path, declared=[_READ_ONLY_DECLARATION])

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch)

    assert (exit_code, calls) == (0, [_ITEM_ID])
    records = _credential_records(repo=repo)
    assert [
        (record["name"], record["capability"], record["provisioning"], record["work_item_id"])
        for record in records
    ] == [(_DECLARED_NAME, "read_only", COPIED_PROVISIONING, _ITEM_ID)]
    # A journal is durable, and the clause requires records to carry names, never
    # values. Asserted over the WHOLE journal rather than this one record, because
    # a value leaking into some other stage's record is the same disclosure.
    assert _DECLARED_VALUE not in json.dumps(_journal_records(repo=repo))


def test_the_declared_name_reaches_the_sandbox_through_the_real_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The projection, read out of the overlay file the production materializer writes.

    The declared line is asserted to land in the SAME `[environments.<id>.env]`
    table as the dispatch credential set, which is the clause's "same channel"
    requirement: a second table, or a second file, would be the second channel it
    forbids.
    """
    monkeypatch.setenv(_DECLARED_NAME, _DECLARED_VALUE)
    _stand_in_host_codex_credential(monkeypatch=monkeypatch)
    repo = _repo(tmp_path=tmp_path, declared=[_READ_ONLY_DECLARATION])
    overlay = tmp_path / "overlay.toml"

    error = materialize_overlay(
        committed=repo / _RESERVED_DIR / "workflow.toml",
        overlay=overlay,
        repo=repo,
        work_item_id=_ITEM_ID,
        dispatch_id="disp-134",
        token=lambda: "test-github-token",
        git_author=GitAuthor(name="Operator", email="operator@example.com"),
    )

    assert error is None
    rendered = overlay.read_text(encoding="utf-8")
    env_table = rendered.split("[environments.fabro-sandbox.env]\n", 1)
    assert len(env_table) == 2
    assert f'{_DECLARED_NAME} = "{_DECLARED_VALUE}"\n' in env_table[1]
    assert "GITHUB_TOKEN = " in env_table[1]


def test_an_overlay_for_a_repository_declaring_nothing_carries_no_such_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control for the projection: the name is the declaration's, not every overlay's.

    The value is present in the environment here too, so the only difference
    between this overlay and the one above is the committed declaration.
    """
    monkeypatch.setenv(_DECLARED_NAME, _DECLARED_VALUE)
    _stand_in_host_codex_credential(monkeypatch=monkeypatch)
    repo = _repo(tmp_path=tmp_path, declared=None)
    overlay = tmp_path / "overlay.toml"

    error = materialize_overlay(
        committed=repo / _RESERVED_DIR / "workflow.toml",
        overlay=overlay,
        repo=repo,
        work_item_id=_ITEM_ID,
        dispatch_id="disp-134",
        token=lambda: "test-github-token",
        git_author=GitAuthor(name="Operator", email="operator@example.com"),
    )

    assert error is None
    assert _DECLARED_NAME not in overlay.read_text(encoding="utf-8")


@pytest.mark.parametrize("fault", sorted(_REFUSED_DECLARATIONS))
def test_a_faulty_declaration_refuses_before_any_run_exists(
    fault: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Each declaration fault refuses with the precondition code, naming the declaration."""
    declaration, named = _REFUSED_DECLARATIONS[fault]
    # Present for every leg, so none of these refusals can be the absent-value one
    # wearing another fault's name.
    monkeypatch.setenv(_DECLARED_NAME, _DECLARED_VALUE)
    monkeypatch.setenv(declaration["name"], "a-value-the-wrapper-injected")
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path, declared=[declaration])

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch)

    assert (exit_code, calls) == (_EXIT_PRECONDITION_ERROR, [])
    stderr = capsys.readouterr().err
    for needle in named:
        assert needle in stderr
    assert _credential_records(repo=repo) == []


def test_a_declared_name_the_wrapper_does_not_inject_refuses_naming_the_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The environment fault, which is the one arm the declaration alone cannot decide.

    The refusal names the target's `credential_wrapper` because injecting the value
    is that wrapper's job and the Dispatcher holds no other route to it.
    """
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path, declared=[_READ_ONLY_DECLARATION])

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch)

    assert (exit_code, calls) == (_EXIT_PRECONDITION_ERROR, [])
    stderr = capsys.readouterr().err
    assert _DECLARED_NAME in stderr
    assert "with-acme-env.sh" in stderr
    assert _credential_records(repo=repo) == []


def test_a_managed_declaration_reaches_the_sandbox_as_the_value_minted_for_this_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The minted projection, read out of the overlay the production materializer writes.

    Three independent facts in one case, because each alone is satisfied by a
    build the others reject. The DOUBLE's ledger says a mint happened once, under
    this run's scope and the declared capability — a projection that invented a
    value would show an empty ledger. The overlay carries the MINTED value — a
    mint whose result was dropped would show a mint in the ledger and no line
    here. And the HOST value, present under the same spelling, is absent from the
    overlay — which is the only thing that distinguishes minting from copying on
    a host that happens to hold a credential of its own.
    """
    monkeypatch.setenv(_MANAGED_NAME, _MANAGED_HOST_VALUE)
    _stand_in_host_codex_credential(monkeypatch=monkeypatch)
    ledger, managed = _provider_double(tmp_path=tmp_path)
    repo = _repo(tmp_path=tmp_path, declared=[_MANAGED_DECLARATION], managed=managed)
    overlay = tmp_path / "overlay.toml"

    error = materialize_overlay(
        committed=repo / _RESERVED_DIR / "workflow.toml",
        overlay=overlay,
        repo=repo,
        work_item_id=_ITEM_ID,
        dispatch_id="disp-134",
        token=lambda: "test-github-token",
        git_author=GitAuthor(name="Operator", email="operator@example.com"),
    )

    assert error is None
    assert _provider_ledger(ledger=ledger) == [f"mint {_MANAGED_NAME} read_only disp-134"]
    rendered = overlay.read_text(encoding="utf-8")
    env_table = rendered.split("[environments.fabro-sandbox.env]\n", 1)
    assert len(env_table) == 2
    assert f'{_MANAGED_NAME} = "acme-minted-disp-134"\n' in env_table[1]
    assert _MANAGED_HOST_VALUE not in rendered


def test_a_minted_credential_is_revoked_after_the_run_and_a_copied_sibling_is_not(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole lifecycle through the real dispatch CLI, with the copied control beside it.

    ORDER IS THE CLAIM, so it is read as a sequence rather than as a set: the
    run-marker line between the mint and the revoke is what makes "revoked AFTER
    the run ends" an observation. A build that revoked before launching, or that
    never revoked at all, produces a ledger this assertion rejects while every
    other signal in the dispatch stays green.

    The SCOPE is the discriminator for "per run": mint and revoke must carry the
    same value, and that value must be this dispatch's own id, read back off the
    journal rather than supplied here — the two legs address the provider by that
    one value and nothing else, so a scope that drifted between them would revoke
    a credential belonging to some other run.

    The COPIED sibling rides in the same declaration. Without it, "the managed
    name is journaled minted" is equally consistent with a build that reports
    every declaration as minted, which would strand the unmanaged one with no
    projected credential at all.
    """
    monkeypatch.setenv(_DECLARED_NAME, _DECLARED_VALUE)
    monkeypatch.setenv(_MANAGED_NAME, _MANAGED_HOST_VALUE)
    _ = _seed_item()
    ledger, managed = _provider_double(tmp_path=tmp_path)
    repo = _repo(
        tmp_path=tmp_path,
        declared=[_MANAGED_DECLARATION, _READ_ONLY_DECLARATION],
        managed=managed,
    )
    calls: list[str] = []

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        calls.append(plan.work_item_id)
        with ledger.open("a", encoding="utf-8") as handle:
            _ = handle.write("run\n")
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="dispatched",
        )

    monkeypatch.setattr(_dispatcher_loop, "run_dispatch", _run_dispatch)

    exit_code = main(
        argv=["dispatch", "--repo", str(repo), "--item", _ITEM_ID, "--no-close-on-merge"]
    )

    assert (exit_code, calls) == (0, [_ITEM_ID])
    records = _journal_records(repo=repo)
    dispatch_ids = [
        record["dispatch_id"] for record in records if record.get("stage") == "dispatch-id"
    ]
    assert len(dispatch_ids) == 1
    scope = dispatch_ids[0]
    assert _provider_ledger(ledger=ledger) == [
        f"mint {_MANAGED_NAME} read_only {scope}",
        "run",
        f"revoke {_MANAGED_NAME} read_only {scope}",
    ]
    assert [
        (record["name"], record["provisioning"]) for record in _credential_records(repo=repo)
    ] == [(_MANAGED_NAME, MINTED_PROVISIONING), (_DECLARED_NAME, COPIED_PROVISIONING)]
    assert [
        (record["name"], record["scope"], record["revoked"])
        for record in records
        if record.get("stage") == _REVOKE_JOURNAL_STAGE
    ] == [(_MANAGED_NAME, scope, True)]
    # Neither the minted value nor the host value it displaced may reach a
    # durable artifact, which the clause requires of every journal and record.
    serialized = json.dumps(records)
    assert f"acme-minted-{scope}" not in serialized
    assert _MANAGED_HOST_VALUE not in serialized


def test_a_provider_that_cannot_mint_refuses_the_dispatch_before_any_run_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A mint that fails refuses, and does NOT slide onto the host's own credential.

    The host holds a value under the same spelling, so the quiet failure mode
    here is a dispatch that proceeds with the COPIED credential: everything stays
    green, the proof stage works, and the only thing lost is the per-run bound
    this clause exists to establish. Asserted on the exit code and on the launch
    seam, because "before any run exists" is a claim about what did NOT happen.

    The ledger is asserted EMPTY, which is the other half: nothing was minted, so
    nothing is left for a revoke to chase. The refusal is read off the dispatch
    RESULT LINE and off the journal, and asserted to name the committed key an
    operator has to edit while carrying neither the host value nor the provider's
    own output — the mint command's stdout IS a credential.
    """
    monkeypatch.setenv(_MANAGED_NAME, _MANAGED_HOST_VALUE)
    _stand_in_host_codex_credential(monkeypatch=monkeypatch)
    _ = _seed_item()
    ledger, managed = _refusing_provider_double(tmp_path=tmp_path)
    repo = _repo(tmp_path=tmp_path, declared=[_MANAGED_DECLARATION], managed=managed)

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch)

    assert (exit_code, calls) == (1, [])
    assert _provider_ledger(ledger=ledger) == []
    reported = capsys.readouterr()
    assert "run-config-overlay" in reported.out
    assert _MANAGED_NAME in reported.out
    assert "quota exhausted" not in reported.out + reported.err
    assert _MANAGED_HOST_VALUE not in reported.out + reported.err


def test_the_drain_reaches_the_same_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two dispatch paths reach the gate through separate call sites.

    Wired into only one of them, a repository whose declaration is unusable would
    be refused through `dispatch` and projected through `loop`, which is the
    failure the pairing exists to exclude.
    """
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path, declared=[_READ_ONLY_DECLARATION])

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch, subcommand="loop")

    assert (exit_code, calls) == (_EXIT_PRECONDITION_ERROR, [])
