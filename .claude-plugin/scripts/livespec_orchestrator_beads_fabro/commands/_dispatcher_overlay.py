"""Run-config overlay rendering for the Dispatcher.

The run goal itself is assembled in `_dispatcher_goal`, and
`escape_minijinja_literal` — the shared escaper that renderer routes untrusted
prose through — now LIVES in `_dispatcher_minijinja_escape`. It was hosted here
and was always a guest: this module renders a run config and renders none of its
own output through the escaper. It moved out by COHESION when the sandbox
worktree-pack prepare step below needed room under this file's LLOC ceiling
(bd-ib-tlmq3m), and deliberately left NO re-export shim behind — a shim would
have bought none of the room the split was for.

`harness_shell_env_lines` now LIVES in `_dispatcher_harness_shell_policy`, which
owns the harness shell-tool policy's keys and both of its projections — the env
table line and the sandbox `local` settings file — and it is re-exported here
because that is where every caller already reaches for it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_auth_projection import (
    codex_auth_env_lines,
    codex_auth_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_otel_config import (
    codex_otel_env_lines,
    codex_otel_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_projection import (
    CredentialUseDeclaration,
    CredentialUseProjection,
    credential_use_env_lines,
    credential_use_guard_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_default_branch_fetch import (
    default_branch_fetch_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_provenance import (
    factory_run_id_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    refreshing_gh_env_lines,
    refreshing_gh_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_author import (
    GitAuthor,
    git_author_env_lines,
    git_identity_prepare_steps_block,
    resolve_workflow_git_author,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_git_credential_helper import (
    git_credential_helper_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_harness_shell_policy import (
    harness_settings_prepare_steps_block,
    harness_shell_env_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_limit_program import (
    hook_limit_prepare_steps_block,
    resolve_publish_draft_limit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_sandbox_image import (
    resolve_sandbox_image,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import (
    SIBLING_CLONES_ROOT_ENV_VAR,
    SiblingClones,
    core_plugin_env_line,
    sibling_clone_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plugin_cache_gate import (
    plugin_cache_gate_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_metadata import (
    PublicationMetadata,
    publication_metadata_env_lines,
    publication_metadata_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    ResumeCheckout,
    resume_checkout_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    COMMITTED_RUN_CONFIG_IMAGE,
    SandboxImageSource,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tmux_socket_root import (
    tmux_tmpdir_env_lines,
    tmux_tmpdir_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_toml_read import (
    toml_section_string,
)

__all__: list[str] = [
    "CURRENCY_GATE_ENV_VALUE",
    "CURRENCY_GATE_ENV_VAR",
    "harness_shell_env_lines",
    "render_run_config_overlay",
    "workflow_graph_path",
]

# Factory dispatch makes undeterminable plugin currency fail hard inside every
# sandbox, matching livespec core Design D2. This is non-secret policy, not a
# credential.
CURRENCY_GATE_ENV_VAR = "LIVESPEC_CURRENCY_GATE"
CURRENCY_GATE_ENV_VALUE = "fail"


def workflow_graph_path(*, committed_text: str, workflow_dir: Path) -> Path | None:
    """The absolute graph path a committed run config declares; None when absent.

    Shared with the payload materializer, which renders that graph's
    timeouts into the per-dispatch payload — so both readers resolve the
    same declared file rather than each assuming the conventional name.
    """
    graph_value = toml_section_string(text=committed_text, section="workflow", key="graph")
    if graph_value is None:
        return None
    return _absolute_graph(graph_value=graph_value, workflow_dir=workflow_dir)


def _absolute_graph(*, graph_value: str, workflow_dir: Path) -> Path:
    graph_path = Path(graph_value)
    return graph_path if graph_path.is_absolute() else workflow_dir / graph_path


def render_run_config_overlay(  # noqa: PLR0913, PLR0915 — kw-only pure overlay builder; each field is an independent projection input.
    *,
    committed_text: str,
    workflow_dir: Path,
    token: str,
    github_token: str,
    siblings: SiblingClones | None,
    otel_env: dict[str, str] | None = None,
    codex_auth_snapshot: str | None = None,
    codex_otel_config: str | None = None,
    sandbox_image: SandboxImageSource = COMMITTED_RUN_CONFIG_IMAGE,
    graph_override: Path | None = None,
    graph_artifact: Path | None = None,
    warn: Callable[[str], object] | None = None,
    prepare_inputs: Mapping[str, str] | None = None,
    dispatch_id: str | None = None,
    proof_store_env: str = "",
    proof_credentials_env: str = "",
    git_author: GitAuthor | None = None,
    credential_use: CredentialUseDeclaration | None = None,
    resume_checkout: ResumeCheckout | None = None,
    publication_metadata: PublicationMetadata | None = None,
) -> str | None:
    """Render the dispatch-time run-config overlay.

    Rewrites the workflow graph path to an absolute path and appends the
    run-scoped env table plus optional sibling-clone and Codex-auth prepare
    steps. Returns None when the committed TOML shape is unusable.

    `graph_override` points the run at the PER-DISPATCH payload's rendered
    graph — the copy carrying this dispatch's resolved node timeouts as
    literal durations — instead of the committed file. Absent (a direct
    caller that materialized no payload), the committed graph is absolutized
    exactly as before.

    `graph_artifact` is WHERE that same graph can be READ, as distinct from
    the name `graph_override` WRITES. The two differ for a package-era client:
    `overlay_graph_reference` names the graph relative to the collected
    package, because the engine refuses an absolute path in an inline file
    reference — and a relative name means "beside the config the engine will
    read", which is not a path this process can open. Reading the limit off
    the written name therefore resolves it against the Dispatcher's own
    working directory, where a repository's OWN `workflow.fabro` is waiting:
    measured pre-fix, that read armed the push at a 900s decoy's duration
    inside a 3600s stage, a bound no dispatch rendered and the node would then
    have named as the limit that ended the push. So only an ABSOLUTE path is
    read, and a reference this process cannot resolve withholds the figure
    rather than resolving it against wherever it happens to be standing.

    `warn` receives the ONE line a withheld figure writes. Withholding stays
    correct — an invented bound would be enforced and then reported as the
    limit that ended the push — but every step of the degradation is silent by
    design (no figure, so no figures file, so the node's own guard pushes
    unbounded), which is what let a bound that never armed look exactly like
    one that did. A caller passing none keeps the pure-projection behaviour.

    `dispatch_id` is the PRE-LAUNCH id the sandbox declares as its
    factory-provenance marker. It is injected here rather than in the
    committed `workflow.toml` because that file is forked per repository, so
    only the overlay reaches every dispatch — see
    `_dispatcher_factory_provenance` for that rationale and for why the Fabro
    run id cannot serve.

    `publication_metadata` is the pull-request title and body the scripted `pr`
    stage applies. It arrives rendered rather than being derived here, because
    the derivation reads a WORK-ITEM and this builder is handed none — and a
    caller that renders none projects no title line and no body step, which is
    exactly the overlay every direct caller rendered before.

    `credential_use` carries the three enforcement inputs a protected sandbox
    needs: the absolute credential-use deadline, the observed credential expiry,
    and the lifetime this dispatch requires. A credential projected WITHOUT them
    is broken protection rather than a legitimate configuration — the sandbox
    would hold a live credential under no bound — so this returns None instead,
    which the dispatch path reports as a pre-launch refusal. That refusal tests
    for the PROTECTED value specifically, not merely for `None`: an
    `UnprotectedCredentialUse` beside a projected snapshot is the same broken
    protection spelled as a declaration, and a `None`-only test would admit it.
    A caller projecting NO Codex credential passes a declaration saying so,
    which installs the guard with no deadline for it to enforce; a caller
    projecting nothing at all passes None for both, which renders no guard and
    leaves ordinary execution untouched.
    """
    if codex_auth_snapshot is not None and not isinstance(credential_use, CredentialUseProjection):
        return None
    graph_value = toml_section_string(text=committed_text, section="workflow", key="graph")
    environment_id = toml_section_string(text=committed_text, section="run.environment", key="id")
    if graph_value is None or environment_id is None:
        return None
    resolved_graph = (
        _absolute_graph(graph_value=graph_value, workflow_dir=workflow_dir)
        if graph_override is None
        else graph_override
    )
    needle = f'graph = "{graph_value}"'
    if needle not in committed_text:
        return None
    rewritten = committed_text.replace(needle, f'graph = "{resolved_graph}"', 1)
    rewritten = resolve_sandbox_image(
        text=rewritten,
        environment_id=environment_id,
        sandbox_image=sandbox_image,
    )
    if rewritten is None:
        return None
    rewritten = resolve_workflow_git_author(committed_text=rewritten, author=git_author)
    if rewritten is None:
        return None
    rewritten = _substitute_input_tokens(text=rewritten, prepare_inputs=prepare_inputs)
    token_literal = json.dumps(token)
    github_token_literal = json.dumps(github_token)
    sibling_steps = "" if siblings is None else sibling_clone_steps_block(siblings=siblings)
    sibling_env_line = (
        ""
        if siblings is None
        else f"{SIBLING_CLONES_ROOT_ENV_VAR} = {json.dumps(siblings.clones_root)}\n"
    )
    currency_gate_env_line = f"{CURRENCY_GATE_ENV_VAR} = {json.dumps(CURRENCY_GATE_ENV_VALUE)}\n"
    core_plugin_env = core_plugin_env_line(siblings=siblings)
    otel_env_lines = _otel_env_lines(otel_env=otel_env)
    tmux_steps = tmux_tmpdir_prepare_steps_block()
    tmux_env_line = tmux_tmpdir_env_lines()
    harness_shell_env = harness_shell_env_lines()
    # The SAME policy keys the env table above renders, projected a second way:
    # as the sandbox's own `local` settings source. The table alone was not the
    # effective ceiling, because the sandbox agent loads the governed
    # repository's committed project settings, whose `env` overrides the process
    # environment it inherits (bd-ib-rv2jk4).
    harness_settings_steps = harness_settings_prepare_steps_block()
    gh_refresh_steps = refreshing_gh_prepare_steps_block()
    gh_refresh_env_lines = refreshing_gh_env_lines()
    # Rendered immediately after the wrapper it routes to, and unconditionally:
    # the Petri-era runner performs no Git operations of its own, so without this
    # every in-sandbox push reaches origin with no credential (bd-ib-52zt3o).
    git_credential_helper_steps = git_credential_helper_prepare_steps_block()
    codex_steps = codex_auth_prepare_steps_block(codex_auth_snapshot=codex_auth_snapshot)
    codex_env_lines = codex_auth_env_lines(codex_auth_snapshot=codex_auth_snapshot)
    codex_otel_steps = codex_otel_prepare_steps_block(codex_otel_config=codex_otel_config)
    codex_otel_env = codex_otel_env_lines(codex_otel_config=codex_otel_config)
    # The hook-limit observer rides the SAME root as the plugin-cache gate's
    # publication helpers, and its limit is read back off the very file this run
    # will execute, whose `publish_draft` attribute carries the literal duration
    # the engine will enforce. Reading the artifact is what keeps the bound the
    # node puts on its own push and the bound the engine imposes from being two
    # numbers nothing proves agree -- which is why it reads `graph_artifact`
    # rather than `resolved_graph`: the latter is the NAME the config carries,
    # and for a package-era client that name is relative to a directory this
    # process is not standing in.
    plugin_cache_steps = plugin_cache_gate_prepare_steps_block() + hook_limit_prepare_steps_block(
        limit_seconds=resolve_publish_draft_limit(
            graph_artifact=graph_artifact, written_graph=resolved_graph, warn=warn
        )
    )
    factory_provenance_steps = factory_run_id_prepare_steps_block(dispatch_id=dispatch_id)
    # Rendered FIRST among the Dispatcher-materialized steps, which puts it
    # immediately after the committed `git fetch --unshallow` whose single-branch
    # refspec it completes. Every later step and every graph node that diffs the
    # dispatch base then sees the ref, rather than depending on which of them the
    # agent happened to reach first.
    dispatch_base_steps = default_branch_fetch_prepare_steps_block(prepare_inputs=prepare_inputs)
    author_env_lines = git_author_env_lines(author=git_author)
    # Rendered immediately after the dispatch base, so EVERY later step and every
    # node that commits — publish_draft's refresh rebase, the needs_human
    # preservation commit — finds the clone already carrying a committer. The
    # Petri-era engine configures only its own checkpoint commits (bd-ib-lsr3vf).
    git_identity_steps = git_identity_prepare_steps_block(author=git_author)
    # Rendered LAST among the prepare steps, so the startup check observes the
    # time preparation itself consumed. Placed earlier it would forgive exactly
    # the queue-and-prepare aging it exists to catch.
    # The resume checkout is appended LAST among the prepare steps, after the
    # committed provisioning: every committed step acts on `.git` or on untracked
    # state a checkout does not disturb, while a checkout performed BEFORE the
    # unshallow would be unshallowed out from under. For an ordinary dispatch it
    # renders the empty string, so no other dispatch sees a byte of it.
    resume_checkout_steps = resume_checkout_prepare_steps_block(checkout=resume_checkout)
    credential_use_steps = credential_use_guard_prepare_steps_block(projection=credential_use)
    credential_use_env = credential_use_env_lines(projection=credential_use)
    # The publish branch the `publish_draft` COMMAND node pushes, plus the resolved
    # proof asset store the `proof_capture` node uploads through. A command node
    # cannot read the rendered goal and `CONTRACT_INPUT_NAMES` is closed, so this
    # env table is the seam — the same one `LIVESPEC_GIT_AUTHOR_NAME` above already
    # uses for the needs_human node's emergency commit (S5 / bd-ib-b4u6b7).
    return (
        rewritten
        + dispatch_base_steps
        + git_identity_steps
        + factory_provenance_steps
        + sibling_steps
        + tmux_steps
        + harness_settings_steps
        + gh_refresh_steps
        + git_credential_helper_steps
        + codex_steps
        + codex_otel_steps
        + plugin_cache_steps
        + resume_checkout_steps
        + credential_use_steps
        # The pull-request body, materialized as a FILE because the stage hands
        # it to `gh pr edit --body-file`. Its path is resolved by shell
        # expansion at both ends rather than projected into the env table: the
        # sandbox plugins root is not known host-side and the pinned engine
        # expands no `${...}` in an env value.
        + publication_metadata_prepare_steps_block(metadata=publication_metadata)
        + "\n# --- Dispatcher-materialized run-scoped credential projection"
        + "\n# --- (UNCOMMITTED; mode 600; deleted when the run returns) ---\n"
        + f"[environments.{environment_id}.env]\n"
        + f"CLAUDE_CODE_OAUTH_TOKEN = {token_literal}\n"
        + f"GITHUB_TOKEN = {github_token_literal}\n"
        + author_env_lines
        + tmux_env_line
        + harness_shell_env
        + gh_refresh_env_lines
        + sibling_env_line
        + core_plugin_env
        + currency_gate_env_line
        + otel_env_lines
        + codex_env_lines
        + codex_otel_env
        + credential_use_env
        + proof_store_env
        # A resumed clone has no publication file from the earlier run. Both
        # publication stages consume this validated anchor as their fallback;
        # never infer it from a branch tip that may have moved since validation.
        + (
            ""
            if resume_checkout is None
            else f"LIVESPEC_RESUME_PUBLISHED_HEAD = {json.dumps(resume_checkout.head)}\n"
        )
        # The rendered pull-request TITLE, beside the publish branch the same
        # stage reads. Both are facts about this dispatch that a command node
        # cannot read off the rendered goal, which is why this table is the
        # seam for them.
        + publication_metadata_env_lines(metadata=publication_metadata)
        # The repository's declared proof credentials, rendered inline in THIS
        # table rather than through a second channel: the pinned engine offers no
        # secret-reference syntax, so the transport is the same uncommitted,
        # mode-600 overlay the credential set above already rides (S8).
        + proof_credentials_env
    )


# The `{{ inputs.<name> }}` token the committed run config templates its prepare
# commands with. The name grammar is deliberately narrow (an identifier), so a
# MiniJinja expression this substituter does not understand is left for whatever
# does.
_INPUT_TOKEN_RE = re.compile(r"\{\{\s*inputs\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _substitute_input_tokens(*, text: str, prepare_inputs: Mapping[str, str] | None) -> str:
    """Render the run config's `inputs.*` tokens HOST-SIDE, because the engine does not.

    fabro 0.254.0 renders `inputs.*` in graph node attributes at run-create time
    and leaves `run.prepare` commands verbatim, so a templated prepare step
    reaches bash as a literal `{{` and kills the run in setup at exit 127 before
    any agent node runs. The committed payload has templated its toolchain and
    conformance premises that way since the typed-integration-contract change,
    which made every dispatch through it unrunnable.

    Substituting here rather than asking the engine to change keeps the values
    on the one already-resolved `ResolvedIntegrationContract` the `--input`
    pairs are rendered from, so the run config and the run's bound inputs cannot
    drift apart. The `--input` pairs are still sent: they are what the GRAPH
    reads, and the graph half works.

    A name the mapping does not carry is LEFT ALONE rather than blanked. An
    unresolved premise then fails visibly at its own step, instead of quietly
    becoming a no-op — which is the failure mode that made the sibling
    conformance-gate defect dangerous.
    """
    if not prepare_inputs:
        return text
    rendered: list[str] = []
    cursor = 0
    for match in _INPUT_TOKEN_RE.finditer(text):
        value = prepare_inputs.get(match.group(1))
        if value is None:
            continue
        rendered.append(text[cursor : match.start()])
        rendered.append(_escape_toml_basic_string(value=value))
        cursor = match.end()
    rendered.append(text[cursor:])
    return "".join(rendered)


def _escape_toml_basic_string(*, value: str) -> str:
    """Escape a substituted value for the TOML basic string it lands inside.

    Every token sits within `script = "..."`. Contract values arrive as one
    shell word-list from `shlex.join`, and `shlex.quote` emits the `'"'"'`
    sandwich for an embedded apostrophe — which carries double quotes. Written
    raw, one of those terminates the TOML string early and makes the WHOLE
    overlay unparseable, turning one repository's command into a dispatch-wide
    failure. Backslash first, so the quote escape is not re-escaped.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _otel_env_lines(*, otel_env: dict[str, str] | None) -> str:
    """Render the in-sandbox CC OTel env keys as `[environments.<id>.env]` lines.

    Empty string when `otel_env` is None (the pre-29f.3 token-only shape).
    Keys are sorted for a stable overlay and each value is `json.dumps`-ed
    so any special character (e.g. the `=`/`,` in OTEL_RESOURCE_ATTRIBUTES,
    the `:` in the endpoint, the `/` in `http/json`) is TOML-quoted
    correctly. These are all NON-secret values — the Honeycomb ingest key
    is never among them (the sandbox ships plaintext to the host-local
    receiver; telemetry design §3.5).
    """
    if otel_env is None:
        return ""
    return "".join(f"{key} = {json.dumps(otel_env[key])}\n" for key in sorted(otel_env))
