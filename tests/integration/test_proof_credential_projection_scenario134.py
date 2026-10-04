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
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_codex_auth,
    _dispatcher_credentials,
    _dispatcher_loop,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_proof_credential_providers as credential_providers,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import materialize_overlay
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_providers import (
    PROOF_CREDENTIAL_REVOKE_STAGE,
    MintedProofCredential,
    ProofCredentialLease,
)
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


def _repo(*, tmp_path: Path, declared: list[dict[str, str]] | None) -> Path:
    """A governed target whose committed configuration declares `proof_credentials`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    dispatcher: dict[str, object] = {"wip_cap": 3, "acceptance_mode": "ai-only"}
    if declared is not None:
        dispatcher["proof_credentials"] = declared
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


def _recording_run_dispatch(
    *, calls: list[str], timeline: list[str] | None = None
) -> Callable[..., DispatchOutcome]:
    """A `run_dispatch` stand-in recording that a factory run WAS created.

    `timeline` is the SHARED event log the provider double below also writes to.
    That sharing is what makes "revoked after the run ends" an observation rather
    than an inference: the mint, the run and the revoke land in one ordered list,
    so a revoke that fired before or during the run is a different list.
    """

    def _run_dispatch(**kwargs: object) -> DispatchOutcome:
        plan = kwargs["plan"]
        assert isinstance(plan, DispatchPlan)
        calls.append(plan.work_item_id)
        if timeline is not None:
            timeline.append(f"run:{plan.work_item_id}")
        return DispatchOutcome(
            work_item_id=plan.work_item_id,
            status="green",
            stage="done",
            pr_number=None,
            merge_sha=None,
            detail="dispatched",
        )

    return _run_dispatch


_MINTED_VALUE = "acme-minted-for-this-run"


@dataclass(kw_only=True)
class _ProviderDouble:
    """A hermetic provider management interface writing to the shared timeline.

    The double is registered into the production registry exactly as a shipped
    adapter would be, which is the only honest way to exercise this path: no
    provider adapter ships in this build, so reaching for a real management
    interface would need a credential and a network and would measure the vendor
    rather than the Dispatcher.
    """

    timeline: list[str]
    mint_refusal: str | None = None
    mint_dispatch_ids: list[str] = field(default_factory=list)

    def mint(self, *, name: str, capability: str, dispatch_id: str) -> MintedProofCredential | str:
        self.timeline.append(f"mint:{name}")
        self.mint_dispatch_ids.append(dispatch_id)
        if self.mint_refusal is not None:
            return self.mint_refusal
        return MintedProofCredential(
            name=name,
            capability=capability,
            value=_MINTED_VALUE,
            revocation_handle=f"handle-for-{name}",
        )

    def revoke(self, *, minted: MintedProofCredential) -> str | None:
        self.timeline.append(f"revoke:{minted.name}")
        return None


def _register_provider(*, monkeypatch: pytest.MonkeyPatch, provider: _ProviderDouble) -> None:
    """Register the double for the declared name, as a shipped adapter would be."""
    monkeypatch.setattr(
        credential_providers, "PROOF_CREDENTIAL_PROVIDERS", {_DECLARED_NAME: provider}
    )


def _dispatch(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    subcommand: str = "dispatch",
    timeline: list[str] | None = None,
) -> tuple[int, list[str]]:
    """Drive one real dispatch and report its exit code plus what it launched."""
    calls: list[str] = []
    monkeypatch.setattr(
        _dispatcher_loop,
        "run_dispatch",
        _recording_run_dispatch(calls=calls, timeline=timeline),
    )
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


def test_a_provider_backed_declaration_is_minted_for_the_run_and_revoked_after_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The minted route, end to end through the real dispatch CLI.

    The ORDER is the load-bearing assertion. "Revokes it after the run ends" is a
    claim about SEQUENCE, and every cheaper instrument is satisfied by a build
    that revokes too early: a recorded revoke call proves only that one happened,
    and a journal record carrying `revoked: true` proves only that one was
    written. The mint, the run and the revoke therefore share ONE ordered
    timeline, so a revoke that fired before the sandbox launched — which would
    hand the proof stage a dead credential while every other assertion still
    passed — produces a different list.

    The declared value is deliberately ABSENT from the environment, which the
    module fixture guarantees. That is what makes this the minted path rather
    than a copied one wearing its name: nothing but the provider could have
    supplied a value here, so the dispatch proceeding at all is evidence the mint
    ran, and the journal's `minted` is evidence the Dispatcher knows it did.
    """
    timeline: list[str] = []
    provider = _ProviderDouble(timeline=timeline)
    _register_provider(monkeypatch=monkeypatch, provider=provider)
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path, declared=[_READ_ONLY_DECLARATION])

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch, timeline=timeline)

    assert (exit_code, calls) == (0, [_ITEM_ID])
    assert timeline == [
        f"mint:{_DECLARED_NAME}",
        f"run:{_ITEM_ID}",
        f"revoke:{_DECLARED_NAME}",
    ]
    # One credential per RUN, carrying this dispatch's own id: a mint that
    # ignored it would be indistinguishable from one long-lived credential
    # fetched once and reused across every dispatch.
    assert len(provider.mint_dispatch_ids) == 1
    assert provider.mint_dispatch_ids[0] != ""
    assert [
        (record["name"], record["provisioning"]) for record in _credential_records(repo=repo)
    ] == [(_DECLARED_NAME, MINTED_PROVISIONING)]
    assert [
        (record["name"], record["revoked"], record["work_item_id"])
        for record in _journal_records(repo=repo)
        if record.get("stage") == PROOF_CREDENTIAL_REVOKE_STAGE
    ] == [(_DECLARED_NAME, True, _ITEM_ID)]
    # A journal is durable, and the clause requires records to carry names, never
    # values. Asserted over the WHOLE journal, since a minted value leaking into
    # some other stage's record is the same disclosure.
    assert _MINTED_VALUE not in json.dumps(_journal_records(repo=repo))


def test_a_declaration_with_no_provider_is_still_copied_and_journaled_as_copied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The COPIED control for the case above, with the registry left empty.

    Without it, "the declaration was journaled minted" is equally consistent with
    a build that journals every declaration minted — and the clause's whole
    journal requirement is that a reader can tell the two routes apart. The only
    difference between this dispatch and the minted one is the registry: the
    identical declaration, the identical item, the identical CLI.

    It is also the regression control for every repository that already declares
    a proof credential. The clause makes minting a SHOULD conditioned on the
    provider offering a management interface, so a declaration without one must
    come out exactly as it did before: copied from the wrapper-supplied
    environment, journaled `copied`, and with no revoke record at all.
    """
    monkeypatch.setenv(_DECLARED_NAME, _DECLARED_VALUE)
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path, declared=[_READ_ONLY_DECLARATION])

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch)

    assert (exit_code, calls) == (0, [_ITEM_ID])
    assert [
        (record["name"], record["provisioning"]) for record in _credential_records(repo=repo)
    ] == [(_DECLARED_NAME, COPIED_PROVISIONING)]
    assert [
        record
        for record in _journal_records(repo=repo)
        if record.get("stage") == PROOF_CREDENTIAL_REVOKE_STAGE
    ] == []


def test_a_refused_mint_fails_the_dispatch_at_its_own_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A provider that mints nothing stops the dispatch instead of falling back.

    The fallback is the shape worth excluding explicitly: copying the host's own
    long-lived credential when the mint fails would silently undo the clause for
    exactly the declarations it governs, and the dispatch would exit 0 looking
    perfectly healthy. The launch seam is read directly, because "no run exists"
    is a claim about what did NOT happen.

    This stage refuses with the ordinary dispatch-failure code rather than the
    pre-dispatch precondition one, and the difference is not cosmetic: the mint
    needs this dispatch's own id, so it necessarily runs per item alongside the
    GitHub App token mint and the overlay write, after target selection has
    already succeeded.

    THE PROJECTION RECORD STILL SAYS `minted`, AND THAT IS CORRECT — asserted
    here rather than left to surprise a reader. That record states the ROUTE the
    declaration resolved to, and the selection gate writes it before any overlay
    exists; the same is true of a `copied` record, whose overlay write can fail
    afterwards too. So it was never a claim that bytes reached a sandbox. The
    record that WOULD be such a claim is the revoke record, which exists only
    once a credential was actually issued — and its absence here is the
    discriminator this case turns on.
    """
    timeline: list[str] = []
    _register_provider(
        monkeypatch=monkeypatch,
        provider=_ProviderDouble(timeline=timeline, mint_refusal="the management API returned 503"),
    )
    _ = _seed_item()
    repo = _repo(tmp_path=tmp_path, declared=[_READ_ONLY_DECLARATION])

    exit_code, calls = _dispatch(repo=repo, monkeypatch=monkeypatch, timeline=timeline)

    assert (exit_code, calls) == (1, [])
    assert timeline == [f"mint:{_DECLARED_NAME}"]
    out = capsys.readouterr().out
    assert "proof-credential-mint" in out
    assert _DECLARED_NAME in out
    assert "the management API returned 503" in out
    assert [
        (record["name"], record["provisioning"]) for record in _credential_records(repo=repo)
    ] == [(_DECLARED_NAME, MINTED_PROVISIONING)]
    # No credential was ever issued, so none is recorded as revoked. This is the
    # assertion that separates a refused mint from the successful case above,
    # where the identical projection record sits beside a revoke record.
    assert [
        record
        for record in _journal_records(repo=repo)
        if record.get("stage") == PROOF_CREDENTIAL_REVOKE_STAGE
    ] == []


def test_the_minted_value_reaches_the_sandbox_through_the_real_overlay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The minted projection, read out of the overlay file the materializer writes.

    The environment deliberately carries a DIFFERENT value under the same name,
    so the projected line is evidence the LEASE won rather than evidence that
    some value happened to be available: a build that ignored the lease would
    render the host's long-lived copy here and produce an overlay of identical
    shape. The assertion is on the rendered bytes in the same
    `[environments.<id>.env]` table as the dispatch credential set, which is the
    clause's same-channel requirement.
    """
    monkeypatch.setenv(_DECLARED_NAME, "the-hosts-own-long-lived-copy")
    _register_provider(monkeypatch=monkeypatch, provider=_ProviderDouble(timeline=[]))
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
        proof_credential_lease=ProofCredentialLease(
            minted=(
                MintedProofCredential(
                    name=_DECLARED_NAME,
                    capability="read_only",
                    value=_MINTED_VALUE,
                    revocation_handle="handle-134",
                ),
            )
        ),
    )

    assert error is None
    env_table = overlay.read_text(encoding="utf-8").split("[environments.fabro-sandbox.env]\n", 1)
    assert len(env_table) == 2
    assert f'{_DECLARED_NAME} = "{_MINTED_VALUE}"\n' in env_table[1]
    assert "the-hosts-own-long-lived-copy" not in env_table[1]


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
