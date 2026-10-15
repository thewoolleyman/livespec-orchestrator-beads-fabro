"""Credential and sandbox sibling-clone preparation for the Dispatcher."""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from livespec_runtime.github_auth.errors import GithubAppAuthError

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_overlay_leg import (
    project_codex_overlay_leg,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_routing import (
    codex_routing_for_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_env import (
    check_credential_env,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    select_factory_credential,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import GitAuthor
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    GITHUB_TOKEN_ENV_VAR,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_write import (
    write_routed_overlay,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    cc_otel_overlay_env,
    render_run_config_overlay,
    resolve_sandbox_otel_endpoint,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_lease import (
    mint_proof_credentials,
    revoke_proof_credentials,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_credential_projection import (
    proof_credentials_overlay_env,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_precondition import (
    proof_store_env_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    PublicationMetadata,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    ResumeCheckout,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    COMMITTED_RUN_CONFIG_IMAGE,
    SandboxImageSource,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    SecretChannelRefusal,
    VaultSecretSink,
    resolve_secret_channel,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sibling_clones import (
    fetch_fleet_manifest_text,
    resolve_sibling_clones,
)
from livespec_orchestrator_beads_fabro.commands._fabro_client import overlay_graph_reference
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)
from livespec_orchestrator_beads_fabro.store import (
    WorkItemComment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "fetch_fleet_manifest_text",
    "materialize_overlay",
    "read_dispatch_comments",
    "read_dispatch_labels",
    "resolve_sibling_clones",
]

_GITHUB_TOKEN_ENV = GITHUB_TOKEN_ENV_VAR  # single-sourced from _dispatcher_io
_LEDGER_READ_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def read_dispatch_comments(
    *,
    repo: Path,
    item: WorkItem,
) -> tuple[WorkItemComment, ...] | str:
    """Read the item's ledger comments for the goal; error string on failure.

    Comments are operator riders appended after filing (e.g.
    pre-authorizations); a brief without them silently re-creates bn4
    finding (c), so a failed read REFUSES the dispatch (error-as-data,
    routed at the `ledger-comments` stage) instead of proceeding
    comment-blind.
    """
    comments = attempt(
        action=lambda: read_work_item_comments(path=store_config(repo=repo), work_item_id=item.id),
        exceptions=_LEDGER_READ_ERRORS,
    )
    if isinstance(comments, AttemptFailure):
        return (
            f"ledger comments read failed for {item.id} "
            f"({type(comments.error).__name__}: {comments.error})"
        )
    return comments


def read_dispatch_labels(
    *,
    repo: Path,
    item: WorkItem,
) -> tuple[str, ...] | str:
    """Read raw beads labels that carry per-item dispatcher policy overrides."""
    record = attempt(
        action=lambda: make_beads_client(config=store_config(repo=repo)).show_issue(
            issue_id=item.id
        ),
        exceptions=_LEDGER_READ_ERRORS,
    )
    if isinstance(record, AttemptFailure):
        return (
            f"ledger label read failed for {item.id} "
            f"({type(record.error).__name__}: {record.error})"
        )
    labels = record.get("labels")
    if not isinstance(labels, list):
        return ()
    raw_labels = cast("list[object]", labels)
    return tuple(label for label in raw_labels if isinstance(label, str))


def materialize_overlay(  # noqa: PLR0911, PLR0913 — kw-only overlay materializer; each argument is an independent projection input, matching `render_run_config_overlay` it feeds, and each return is one PRE-LAUNCH REFUSAL (credential env, App token mint, sibling clones, Codex projection, proof-credential mint, unmaterializable config) that names its own cause to the operator; collapsing any two would report the wrong one.
    *,
    committed: Path,
    overlay: Path,
    repo: Path,
    work_item_id: str,
    dispatch_id: str,
    token: Callable[[], str],
    git_author: GitAuthor,
    review_fix_visit_cap: int,
    graph_override: Path | None = None,
    prepare_inputs: Mapping[str, str] | None = None,
    proof_rendering: str = "",
    adapter_inputs: frozenset[str] = frozenset(),
    resume_checkout: ResumeCheckout | None = None,
    # The pull-request title and body the scripted `pr` stage applies, rendered
    # from the work-item by the caller that holds one. None for a direct caller
    # that holds none, which projects neither and leaves the stage's own
    # absent-title and absent-body sentinels to report the shortfall.
    publication_metadata: PublicationMetadata | None = None,
    # The CLIENT build this dispatch resolved for its factory, which decides how
    # the written config may NAME its graph. None is the pinned-engine posture —
    # the absolute path every overlay has always carried — so a caller that
    # wires nothing renders exactly the config it did before.
    fabro_version: str | None = None,
    # WHICH factory this dispatch launches at, and where a routed credential is
    # stored so the worker can resolve it. Both default to the pinned-engine
    # posture — the implicit single-factory name, and no vault — so a caller that
    # wires neither renders exactly the inline overlay it always did.
    factory_name: str = "default",
    secret_sink: VaultSecretSink | None = None,
    # WHERE this dispatch's sandbox image comes from, as the plan resolved it.
    # The default is the pinned-engine posture — no catalog environment and no
    # configured override, so the committed run config's own image stands
    # byte-for-byte — which is what a caller that wires nothing rendered before
    # this decision existed.
    sandbox_image: SandboxImageSource = COMMITTED_RUN_CONFIG_IMAGE,
) -> str | None:
    """Write the uncommitted mode-600 run-config overlay.

    Returns None on success, or an actionable error message (an expected
    failure routed as data — the dispatch reports it at the
    `run-config-overlay` stage). The overlay is the RUN-SCOPED
    credential projection: the committed config (graph path absolutized)
    plus an appended env table carrying the CLAUDE_CODE_OAUTH_TOKEN
    value read from this process's environment and a GITHUB_TOKEN freshly
    minted from the App installation-token provider (`token` is the
    provider's accessor — the sandbox receives an ephemeral installation
    token, never the durable App key and never a fleet PAT; projected
    under GITHUB_TOKEN, not GH_TOKEN, so fabro's per-exec re-mint is not
    shadowed). Fabro
    `{{ env }}` interpolation is NOT usable here (see the module
    docstring), so the value MUST be materialized. The token never
    reaches a log, journal, or argv; the overlay file is deleted when
    the run returns.

    The overlay ALSO provisions the sandbox sibling clones: one depth-1
    prepare-step clone per fleet member (minus the dispatch target,
    keyed by the `--repo` basename) plus the non-secret
    `LIVESPEC_SIBLING_CLONES_ROOT` env key, so cross-repo checks under
    `just check` resolve family siblings inside the sandbox the same
    way livespec CI provisions them.

    It projects the in-sandbox Claude-Code OTel env (29f.3): the
    `cc_otel_overlay_env` dict carrying the correlation triple
    (`work_item_id` + `dispatch_id`) and the host-local E1 receiver
    endpoint, so CC native telemetry exports from inside the sandbox to
    the host-local enrich/receive stage. All NON-secret values — the
    Honeycomb ingest key is NOT among them (the sandbox ships plaintext;
    the host egress stage holds the key).

    It declares the sandbox's FACTORY PROVENANCE: a prepare step writing
    `dispatch_id` to the sandbox clone's local `livespec.factoryRunId` git
    config, which is what lets the dev-tooling commit gate tell a factory
    commit from a hand-cranked one (`_dispatcher_factory_provenance`).

    Finally it projects the dual-credential Codex snapshot (scenarios.md
    Scenario 18 / Scenario 19): the host `auth.json` is read, freshness-
    gated against the run budget, and projected non-rotatably into the
    sandbox `$CODEX_HOME/auth.json` alongside the Claude OAuth env. A
    missing or too-short-lived host credential refuses the dispatch here
    with an actionable message (naming `codex login`). It renews NOTHING:
    the bounded in-place renewal runs in the pre-dispatch wall's
    credential gate, before the item is claimed, because that is the only
    position from which an unrenewable credential can be reported without
    leaving an `active` row nobody is working.
    """
    # WHAT the written config NAMES its graph, as distinct from WHICH graph this
    # dispatch runs. `graph_override` itself stays absolute — the route check
    # below READS that file — so only the rendered TEXT moves. Projected here,
    # above everything that reads or mints, because it is a pure projection of
    # the arguments and a geometry bug in it must raise where nothing is yet
    # owed back; the package directory is the overlay's own, which for a Petri
    # dispatch IS the package `materialized_workflow_config` placed it in.
    graph_reference = (
        None
        if graph_override is None
        else overlay_graph_reference(
            version=fabro_version, graph=graph_override, package_dir=overlay.parent
        )
    )
    # Resolved FIRST among the steps that read anything, before any credential
    # is read or minted. It is a pure read
    # of committed configuration, so it can only refuse on a declaration the
    # operator can fix, and refusing here leaves nothing behind to clean up.
    channel = resolve_secret_channel(block=dispatcher_block(cwd=repo), factory=factory_name)
    if isinstance(channel, SecretChannelRefusal):
        return channel.message
    env_error = check_credential_env(repo=repo)
    if env_error is not None:
        return env_error
    github_token = attempt(action=token, exceptions=(GithubAppAuthError,))
    if isinstance(github_token, AttemptFailure):
        exc = cast("GithubAppAuthError", github_token.error)
        return f"C-mode dispatch refused: GitHub App token mint failed: {exc.detail}"
    # Refresh the ambient GH_TOKEN so the host-side `gh api` fleet-manifest
    # fetch below runs on a currently-valid installation token too.
    os.environ[_GITHUB_TOKEN_ENV] = github_token
    siblings = resolve_sibling_clones(repo=repo)
    if isinstance(siblings, str):
        return siblings
    sandbox_otel_endpoint = resolve_sandbox_otel_endpoint(environ=dict(os.environ))
    # EVERYTHING THIS DISPATCH PROJECTS INTO ITS SANDBOX `$CODEX_HOME`: the run
    # budget, the graded host snapshot, the credential-use enforcement inputs, the
    # launch-route guard, and the Codex telemetry table. One unit because the order
    # between them is load-bearing, because the credential and the telemetry table
    # must be scoped by ONE routing decision (that module's docstring records the
    # preparation abort that scoping them apart produced), and refused HERE — before
    # the proof-credential mint below — so no refusal in it can leave a live
    # provider credential behind.
    codex_leg = project_codex_overlay_leg(
        committed=committed,
        block=dispatcher_block(cwd=repo),
        review_fix_visit_cap=review_fix_visit_cap,
        graph_override=graph_override,
        adapter_inputs=adapter_inputs,
        # The ONE wall-clock seam the leg reads, held here so the whole dispatch
        # path has a single place a test stands time still.
        clock=lambda: int(time.time()),
        # WHETHER THIS DISPATCH ROUTES ANY NODE TO CODEX, which decides whether
        # there is a credential for the leg to grade and stamp a deadline from,
        # and whether there is a `$CODEX_HOME` for its telemetry table to be
        # written into. Resolved from the SAME pure function the pre-dispatch
        # wall's gate consults, against the same host-side checkout, so the
        # pre-claim and post-claim halves cannot scope themselves differently; it
        # is read here rather than threaded down from the wall because the wall
        # grades a whole selection while this runs per dispatch, and a value
        # carried across that boundary would have to ride every plan and seam
        # between them to reach one call site.
        codex_routing=codex_routing_for_dispatch(repo=repo),
        # The telemetry table's three inputs. The endpoint is the SAME reading the
        # Claude-Code OTel overlay below is rendered from, resolved once above, so
        # the sandbox's two exporters cannot be pointed at different receivers.
        sandbox_otel_endpoint=sandbox_otel_endpoint,
        work_item_id=work_item_id,
        dispatch_id=dispatch_id,
    )
    if isinstance(codex_leg, str):
        return codex_leg
    otel_env = cc_otel_overlay_env(
        work_item_id=work_item_id,
        dispatch_id=dispatch_id,
        endpoint=sandbox_otel_endpoint,
    )
    credential_choice = select_factory_credential(
        environ=os.environ,
        home=Path.home(),
        warn=lambda message: sys.stderr.write(f"livespec-dispatch: {message}\n"),
    )
    # Minted LAST among the steps that can still refuse, so a refusal above this
    # line never leaves a live provider credential behind. The scope is the
    # dispatch id, which is also what the run-teardown revoke is handed.
    lease_runner = ShellCommandRunner()
    minted = mint_proof_credentials(repo=repo, scope=dispatch_id, runner=lease_runner)
    if isinstance(minted, str):
        return minted
    # Hoisted out of the call below so the routed name list can be read back off
    # the lines this projection ACTUALLY rendered. The declaration is read once,
    # by the module that owns it, exactly as it was before the transport moved.
    proof_credentials_env = proof_credentials_overlay_env(
        repo=repo, environ=os.environ, minted=minted
    )
    rendered = render_run_config_overlay(
        committed_text=committed.read_text(encoding="utf-8"),
        workflow_dir=committed.parent.resolve(),
        token=os.environ[credential_choice.env_name],
        github_token=github_token,
        siblings=siblings,
        otel_env=otel_env,
        codex_auth_snapshot=codex_leg.snapshot,
        codex_otel_config=codex_leg.otel_config,
        # WHERE this dispatch's sandbox image comes from, resolved ONCE with the
        # plan and forwarded rather than re-read here. The dispatch record names
        # the same decision, and a second read of the same configuration cannot
        # be proven to agree with the first — the disagreement would be
        # invisible, because both reads produce a well-formed image
        # (bd-ib-jy7fuh).
        sandbox_image=sandbox_image,
        # The per-dispatch payload's rendered graph, carrying this dispatch's
        # resolved node timeouts as literal durations, NAMED as the client that
        # collects it can resolve it.
        graph_override=graph_reference,
        # The publish branch and head a RESUME places the sandbox clone on.
        # None for every other dispatch, which renders no step at all.
        resume_checkout=resume_checkout,
        # The rendered title and body, forwarded rather than derived here: the
        # derivation reads a work-item and this function is handed only an id.
        publication_metadata=publication_metadata,
        # The resolved integration contract's values, substituted into the
        # committed run config's `{{ inputs.* }}` prepare commands because the
        # pinned engine does not render that site. Forwarded rather than
        # re-derived: the caller passes the SAME resolved contract the
        # `--input` pairs come from.
        prepare_inputs=prepare_inputs,
        # The publish branch the `publish_draft` command node pushes, plus this
        # repository's resolved proof asset store. The branch and the tag are
        # resolved HERE, from the single shared derivation and the committed
        # configuration, rather than being spelled a second time (S5 /
        # bd-ib-b4u6b7). The RENDERING cannot be: it is a per-repository forge
        # MEASUREMENT, so it arrives already measured, read back from the record
        # the pre-dispatch gate journaled. Resolving it here would put a forge
        # call on a path every dispatch materializes offline.
        proof_store_env=proof_store_env_lines(
            repo=repo, work_item_id=work_item_id, rendering=proof_rendering
        ),
        # This repository's DECLARED proof credentials, by name, valued from this
        # process's environment. The pre-dispatch gate has already refused every
        # unusable declaration, so what reaches here is admitted; the builder is
        # nonetheless fail-closed and renders nothing it cannot account for (S8).
        # A declaration whose provider exposes a management interface takes the
        # value minted a few lines above; every other one takes the
        # wrapper-supplied value out of this process's environment.
        proof_credentials_env=proof_credentials_env,
        # The pre-launch dispatch id the sandbox declares as its
        # factory-provenance marker. This function runs BEFORE `fabro run`,
        # which is why the marker cannot carry the Fabro run id.
        dispatch_id=dispatch_id,
        git_author=git_author,
        credential_use=codex_leg.credential_use,
    )
    if rendered is None:
        # The credentials minted just above belong to a run that will now never
        # exist, and the run-teardown revoke is only reached once a run starts.
        # Revoking here is what keeps "revoked when the run ends" true of a
        # dispatch that ended before it began.
        revoke_proof_credentials(repo=repo, scope=dispatch_id, runner=lease_runner)
        return (
            f"workflow config {committed} is not materializable: it must carry "
            '[workflow] graph = "..." and [run.environment] id = "..."'
        )
    write_refusal = write_routed_overlay(
        overlay=overlay,
        rendered=rendered,
        channel=channel,
        proof_credentials_env=proof_credentials_env,
        sink=secret_sink,
    )
    if write_refusal is not None:
        # Same reasoning as the unmaterializable-config arm above: this dispatch
        # will never exist, and the run-teardown revoke is only reached once a
        # run starts.
        revoke_proof_credentials(repo=repo, scope=dispatch_id, runner=lease_runner)
    return write_refusal
