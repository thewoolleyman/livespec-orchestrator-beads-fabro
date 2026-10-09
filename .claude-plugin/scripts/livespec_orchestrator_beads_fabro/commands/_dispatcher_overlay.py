"""Run-config overlay rendering (plus MiniJinja literal escaping) for the Dispatcher.

The run goal itself is assembled in `_dispatcher_goal`; this module keeps
`escape_minijinja_literal` — the shared escaper the goal renderer (and any
future MiniJinja-templated text) routes untrusted prose through.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
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
    CredentialUseProjection,
    credential_use_env_lines,
    credential_use_guard_prepare_steps_block,
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
    resolve_workflow_git_author,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_entry import (
    ResumeCheckout,
    resume_checkout_prepare_steps_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_toml_read import (
    toml_section_string,
)

__all__: list[str] = [
    "CURRENCY_GATE_ENV_VALUE",
    "CURRENCY_GATE_ENV_VAR",
    "escape_minijinja_literal",
    "harness_shell_env_lines",
    "render_run_config_overlay",
    "workflow_graph_path",
]

# Factory dispatch makes undeterminable plugin currency fail hard inside every
# sandbox, matching livespec core Design D2. This is non-secret policy, not a
# credential.
CURRENCY_GATE_ENV_VAR = "LIVESPEC_CURRENCY_GATE"
CURRENCY_GATE_ENV_VALUE = "fail"
# MiniJinja's three OPENING delimiters: expression `{{`, statement `{%`,
# comment `{#` (fabro v0.254.0 renders the run goal through MiniJinja —
# fabro issue #124 — storing it in the graph's `goal` attribute and
# interpolating it into the prompts as `{{ goal }}`). The lexer only
# enters template mode at one of these openers; closing delimiters and
# every other character are inert outside a tag. Neutralizing every
# opener therefore guarantees arbitrary goal prose cannot alter graph
# semantics regardless of content (work-item livespec-impl-beads-ajv).
_MINIJINJA_OPEN_DELIMITER_RE = re.compile(r"\{\{|\{%|\{#")


# Sandbox-local tmux socket root. tmux appends its own tmux-<uid>/default
# socket below TMUX_TMPDIR, so bare `tmux kill-server` inside a Fabro sandbox
# resolves only sandbox-local sockets and never the host default under /tmp.
_SANDBOX_TMUX_TMPDIR = "/workspace/.tmux"


# The Claude harness's own shell-tool policy, projected as NON-SECRET
# configuration beside the tmux socket root above.
#
# The harness moves a foreground shell call that REACHES its timeout into a
# background task; the ACP engine then raises `BackgroundedTool` and ENDS the
# turn. So an honest long foreground call — a full pytest run, a coverage pass —
# destroys the stage instead of returning late, and nothing on the agent's side
# can prevent it: the decision is the harness's, taken after the call has
# already run out its clock. Setting this switch makes such a call report back
# as an ordinary timed-out call the agent can read and retry
# (work-item bd-ib-k627ja; plan `pr-stage-backgrounded-push-fault`).
_HARNESS_SHELL_ENV: tuple[tuple[str, str], ...] = (("CLAUDE_CODE_DISABLE_BACKGROUND_TASKS", "1"),)


def harness_shell_env_lines() -> str:
    """Render the harness shell-tool policy as `[environments.<id>.env]` lines.

    Named rather than inlined so the keys and their values have ONE spelling a
    test can bind, the way `_tmux_tmpdir_prepare_steps_block` does for the tmux
    socket root. Each value is `json.dumps`-ed for the same reason every other
    line in that table is: the table is TOML, and a value written raw is a
    parse hazard rather than a string.
    """
    return "".join(f"{name} = {json.dumps(value)}\n" for name, value in _HARNESS_SHELL_ENV)


def escape_minijinja_literal(*, text: str) -> str:
    """Neutralize MiniJinja syntax in `text` so it renders back verbatim.

    Fabro v0.254.0 renders the run goal through MiniJinja (fabro issue
    #124): the goal lands in the graph's `goal` attribute and is
    interpolated into the prompts as `{{ goal }}`. Untrusted item prose
    containing a literal MiniJinja construct — a `{{ ... }}` expression
    (e.g. justfile recipe syntax), a `{% ... %}` statement, or a
    `{# ... #}` comment — would otherwise re-enter template mode and
    raise `template_undefined_variable` (or worse: this is also a mild
    template-INJECTION surface, since the prose could introduce arbitrary
    template constructs). Three v5k-leg dispatches failed pre-flight this
    way (livespec-wwfu, livespec-runtime-ani, livespec-driver-claude-3bk;
    work-item livespec-impl-beads-ajv).

    MiniJinja's lexer only enters template mode at one of the three
    OPENING delimiters (`{{`, `{%`, `{#`); the closing delimiters and
    every other character (backslashes, quotes, newlines) are inert
    outside a tag. So replacing each opener with the MiniJinja expression
    that emits those two literal characters — `{{` -> `{{ "{{" }}`,
    `{%` -> `{{ "{%" }}`, `{#` -> `{{ "{#" }}` — makes the lexer never
    enter a tag from the original prose, and the inserted expressions
    render back to the exact original characters after one render. This
    transform is self-cancelling by construction: it is correct only when
    the consumer renders exactly once, because that render restores the
    original opener text. This is preferred over a `{% raw %}...{% endraw
    %}` wrapper, which is NOT content-agnostic: a goal containing the
    literal text `{% endraw %}` would close the raw block early and
    re-expose the tail. The single `re.sub` pass does not re-scan its own
    replacement text, so the inserted `{{ ... }}` expressions are never
    themselves neutralized during this transform.
    """
    return _MINIJINJA_OPEN_DELIMITER_RE.sub(
        # The replacement always OPENS with the expression delimiter `{{`
        # (only `{{ ... }}` emits a value) and quotes the matched opener as
        # a string literal: `{{` -> `{{ "{{" }}`, `{%` -> `{{ "{%" }}`,
        # `{#` -> `{{ "{#" }}`. Using the matched opener as the prefix would
        # be wrong — `{%`/`{#` are themselves live openers, not literals.
        lambda match: '{{ "' + match.group(0) + '" }}',
        text,
    )


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
    fabro_sandbox_image: str | None = None,
    graph_override: Path | None = None,
    prepare_inputs: Mapping[str, str] | None = None,
    dispatch_id: str | None = None,
    proof_store_env: str = "",
    proof_credentials_env: str = "",
    git_author: GitAuthor | None = None,
    credential_use: CredentialUseProjection | None = None,
    resume_checkout: ResumeCheckout | None = None,
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

    `dispatch_id` is the PRE-LAUNCH id the sandbox declares as its
    factory-provenance marker. It is injected here rather than in the
    committed `workflow.toml` because that file is forked per repository, so
    only the overlay reaches every dispatch — see
    `_dispatcher_factory_provenance` for that rationale and for why the Fabro
    run id cannot serve.

    `credential_use` carries the three enforcement inputs a protected sandbox
    needs: the absolute credential-use deadline, the observed credential expiry,
    and the lifetime this dispatch requires. A credential projected WITHOUT them
    is broken protection rather than a legitimate configuration — the sandbox
    would hold a live credential under no bound — so this returns None instead,
    which the dispatch path reports as a pre-launch refusal. A caller projecting
    NO Codex credential has nothing to bound and passes None for both, which
    renders no guard and no enforcement and leaves ordinary execution untouched.
    """
    if codex_auth_snapshot is not None and credential_use is None:
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
    rewritten = _rewrite_fabro_sandbox_image(
        text=rewritten,
        environment_id=environment_id,
        fabro_sandbox_image=fabro_sandbox_image,
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
    tmux_steps = _tmux_tmpdir_prepare_steps_block()
    tmux_env_line = f"TMUX_TMPDIR = {json.dumps(_SANDBOX_TMUX_TMPDIR)}\n"
    harness_shell_env = harness_shell_env_lines()
    gh_refresh_steps = refreshing_gh_prepare_steps_block()
    gh_refresh_env_lines = refreshing_gh_env_lines()
    codex_steps = codex_auth_prepare_steps_block(codex_auth_snapshot=codex_auth_snapshot)
    codex_env_lines = codex_auth_env_lines(codex_auth_snapshot=codex_auth_snapshot)
    codex_otel_steps = codex_otel_prepare_steps_block(codex_otel_config=codex_otel_config)
    codex_otel_env = codex_otel_env_lines(codex_otel_config=codex_otel_config)
    plugin_cache_steps = plugin_cache_gate_prepare_steps_block()
    factory_provenance_steps = factory_run_id_prepare_steps_block(dispatch_id=dispatch_id)
    author_env_lines = git_author_env_lines(author=git_author)
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
        + factory_provenance_steps
        + sibling_steps
        + tmux_steps
        + gh_refresh_steps
        + codex_steps
        + codex_otel_steps
        + plugin_cache_steps
        + resume_checkout_steps
        + credential_use_steps
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


def _rewrite_fabro_sandbox_image(
    *,
    text: str,
    environment_id: str,
    fabro_sandbox_image: str | None,
) -> str | None:
    """Rewrite only `[environments.<id>.image] docker` when configured."""
    if fabro_sandbox_image is None:
        return text
    section = f"environments.{environment_id}.image"
    committed_image = toml_section_string(text=text, section=section, key="docker")
    if committed_image is None:
        return None
    needle = f'docker = "{committed_image}"'
    if needle not in text:
        return None
    return text.replace(needle, f"docker = {json.dumps(fabro_sandbox_image)}", 1)


def _tmux_tmpdir_prepare_steps_block() -> str:
    script = f"mkdir -p {_SANDBOX_TMUX_TMPDIR} && chmod 700 {_SANDBOX_TMUX_TMPDIR}"
    lines = [
        "",
        "# --- Dispatcher-materialized sandbox-local tmux socket root ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(script)}",
    ]
    return "\n".join(lines) + "\n"


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
