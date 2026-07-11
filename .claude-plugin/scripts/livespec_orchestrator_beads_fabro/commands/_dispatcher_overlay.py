"""Goal and run-config overlay rendering for the Dispatcher."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.store import WorkItemComment

# fmt: off
__all__: list[str] = [
    "CORE_PLUGIN_ROOT_ENV_VAR", "CURRENCY_GATE_ENV_VALUE", "CURRENCY_GATE_ENV_VAR",
    "SIBLING_CLONES_ROOT_ENV_VAR", "SiblingClones", "render_goal",
    "render_run_config_overlay",
]
# fmt: on

SIBLING_CLONES_ROOT_ENV_VAR = "LIVESPEC_SIBLING_CLONES_ROOT"

# The env-var a fleet repo's janitor reads to resolve the livespec CORE plugin
# inside the Fabro sandbox (the console's `check-doctor-static`). The sandbox
# spawns with a fail-closed env allowlist (fabro-server/src/spawn_env.rs) and
# carries no installed-plugin registry, so without this projection a
# CORE-dependent `just check` cannot find core. The Dispatcher's overlay
# projects it at the in-sandbox core-sibling clone path
# (`<clones_root>/livespec/.claude-plugin`); `_CORE_SIBLING_SLUG` is the livespec
# CORE repo's clone slug.
CORE_PLUGIN_ROOT_ENV_VAR = "LIVESPEC_CORE_PLUGIN_ROOT"

# Factory dispatch makes undeterminable plugin currency fail hard inside every
# sandbox, matching livespec core Design D2. This is non-secret policy, not a
# credential.
CURRENCY_GATE_ENV_VAR = "LIVESPEC_CURRENCY_GATE"
CURRENCY_GATE_ENV_VALUE = "fail"
_CORE_SIBLING_SLUG = "livespec"
# MiniJinja's three OPENING delimiters: expression `{{`, statement `{%`,
# comment `{#` (fabro v0.254.0 renders the run goal through MiniJinja —
# fabro issue #124 — storing it in the graph's `goal` attribute and
# interpolating it into the prompts as `{{ goal }}`). The lexer only
# enters template mode at one of these openers; closing delimiters and
# every other character are inert outside a tag. Neutralizing every
# opener therefore guarantees arbitrary goal prose cannot alter graph
# semantics regardless of content (work-item livespec-impl-beads-ajv).
_MINIJINJA_OPEN_DELIMITER_RE = re.compile(r"\{\{|\{%|\{#")


@dataclass(frozen=True, kw_only=True)
class SiblingClones:
    """The per-dispatch sandbox sibling-clone plan.

    `repos` is the fleet member set MINUS the dispatch target (the
    target is already the sandbox workspace clone); `clones_root` is
    the in-sandbox directory the clones land under — the same path the
    overlay projects as `LIVESPEC_SIBLING_CLONES_ROOT`.
    """

    owner: str
    repos: tuple[str, ...]
    clones_root: str


# The sandbox path the projected Codex auth.json is written to. The
# prepare step (running before the agent nodes) writes the credential
# here, and the codex-acp child reads it via $CODEX_HOME — both inherit
# CODEX_HOME from the container-level [environments.<id>.env] table.
_SANDBOX_CODEX_HOME = "/workspace/.codex"


def render_goal(
    *,
    item: WorkItem,
    repo: Path,
    branch: str,
    comments: tuple[WorkItemComment, ...] = (),
    lessons: str = "",
) -> str:
    """Render the per-item brief delivered to the phase graph.

    Item fields, ledger comments, and ratified lessons are assembled, then
    MiniJinja open delimiters are escaped so Fabro renders the prose verbatim.
    """
    gap_line = f"Gap id: {item.gap_id}\n" if item.gap_id is not None else ""
    spec_line = (
        f"Spec id: {item.spec_commitment_hint}\n" if item.spec_commitment_hint is not None else ""
    )
    acceptance_line = (
        f"\nAcceptance criteria:\n{item.acceptance_criteria}\n"
        if item.acceptance_criteria is not None
        else ""
    )
    notes_line = f"\nNotes:\n{item.notes}\n" if item.notes is not None else ""
    base = (
        f"Work-item: {item.id}\n"
        # The agent runs inside the Fabro sandbox's OWN fresh clone (cwd),
        # NOT this path: `repo` is the Dispatcher's host-side checkout (e.g.
        # /workspace/dispatch-target) and does not exist in the sandbox. A
        # bare `Repo: <path>` line let the PR-stage agent cd to the missing
        # host path and report "no committed work" (livespec-vtxt). Keep the
        # path for provenance but frame it unmistakably as NOT a cd target.
        f"Repo (target repository; you are ALREADY inside its isolated Fabro "
        f"sandbox clone — run every git/gh command in your CURRENT WORKING "
        f"DIRECTORY and NEVER cd to this path: it is the dispatcher's "
        f"host-side checkout and does NOT exist inside your sandbox): {repo}\n"
        f"Publish branch (push HEAD to this exact ref at the PR stage): {branch}\n"
        f"Rank: {item.rank}  Type: {item.type}\n"
        f"{gap_line}"
        f"{spec_line}"
        f"Title: {item.title}\n"
        "\n"
        "Description:\n"
        f"{item.description}\n"
        f"{acceptance_line}"
        f"{notes_line}"
    )
    # Ratified lessons (the S1 read side) inject in a clearly delimited
    # section BEFORE escaping, so escape_minijinja_literal neutralizes the
    # human-merged lesson text like every other interpolated field. Empty
    # lessons leave the brief byte-identical (no heading or placeholder
    # bleed-through), matching the fail-open contract.
    body = base
    if lessons:
        body += (
            "\nRatified lessons (human-merged via loop-reflection-gate/"
            "lessons.md; treat as standing guidance for this dispatch):\n"
            f"{lessons}\n"
        )
    # Escape AFTER assembly so EVERY interpolated field (title, description,
    # lessons, comments, repo path) is neutralized in one place: the whole
    # rendered goal is what flows into fabro's MiniJinja-templated graph
    # `goal` attribute and prompts (work-item livespec-impl-beads-ajv).
    if not comments:
        return escape_minijinja_literal(text=body)
    lines = [
        "",
        "Ledger comments (operator riders appended after filing; treat them as part of the brief):",
    ]
    for index, comment in enumerate(comments, start=1):
        lines.append(f"[{index}] {_comment_entry(comment=comment)}")
    return escape_minijinja_literal(text=body + "\n".join(lines) + "\n")


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
    render back to the exact original characters. This is preferred over
    a `{% raw %}...{% endraw %}` wrapper, which is NOT content-agnostic: a
    goal containing the literal text `{% endraw %}` would close the raw
    block early and re-expose the tail. The single `re.sub` pass does not
    re-scan its own replacement text, so the inserted `{{ ... }}`
    expressions are never themselves neutralized — the transform survives
    arbitrary content (nested/doubled delimiters included).
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


def _comment_entry(*, comment: WorkItemComment) -> str:
    """Format one rider as `(author, created_at) text`, dropping absent parts."""
    provenance = ", ".join(
        part for part in (comment.author, comment.created_at) if part is not None
    )
    if provenance == "":
        return comment.text
    return f"({provenance}) {comment.text}"


def _toml_section_string(*, text: str, section: str, key: str) -> str | None:
    """Read one basic-string value from one TOML table, regex-scoped.

    A full TOML parser is unavailable on the pinned Python (tomllib is
    3.11+; the family vendors no TOML library), and the committed run
    config is repo-owned with a stable shape, so a section-scoped regex
    is sufficient and dependency-free.
    """
    section_pattern = re.compile(
        r"(?ms)^\[" + re.escape(section) + r"\][ \t]*\r?$(?P<body>.*?)(?=^\[|\Z)"
    )
    section_match = section_pattern.search(text)
    if section_match is None:
        return None
    key_pattern = re.compile(
        r"(?m)^" + re.escape(key) + r'[ \t]*=[ \t]*"(?P<value>[^"]*)"[ \t]*\r?$'
    )
    key_match = key_pattern.search(section_match.group("body"))
    if key_match is None:
        return None
    return key_match.group("value")


def render_run_config_overlay(  # noqa: PLR0913 — kw-only pure overlay builder; each field is an independent projection input.
    *,
    committed_text: str,
    workflow_dir: Path,
    token: str,
    github_token: str,
    siblings: SiblingClones | None,
    otel_env: dict[str, str] | None = None,
    codex_auth_snapshot: str | None = None,
) -> str | None:
    """Render the dispatch-time run-config overlay.

    Rewrites the workflow graph path to an absolute path and appends the
    run-scoped env table plus optional sibling-clone and Codex-auth prepare
    steps. Returns None when the committed TOML shape is unusable.
    """
    graph_value = _toml_section_string(text=committed_text, section="workflow", key="graph")
    environment_id = _toml_section_string(text=committed_text, section="run.environment", key="id")
    if graph_value is None or environment_id is None:
        return None
    graph_path = Path(graph_value)
    resolved_graph = graph_path if graph_path.is_absolute() else workflow_dir / graph_path
    needle = f'graph = "{graph_value}"'
    if needle not in committed_text:
        return None
    rewritten = committed_text.replace(needle, f'graph = "{resolved_graph}"', 1)
    token_literal = json.dumps(token)
    github_token_literal = json.dumps(github_token)
    sibling_steps = "" if siblings is None else _sibling_clone_steps_block(siblings=siblings)
    sibling_env_line = (
        ""
        if siblings is None
        else f"{SIBLING_CLONES_ROOT_ENV_VAR} = {json.dumps(siblings.clones_root)}\n"
    )
    currency_gate_env_line = f"{CURRENCY_GATE_ENV_VAR} = {json.dumps(CURRENCY_GATE_ENV_VALUE)}\n"
    core_plugin_env_line = _core_plugin_env_line(siblings=siblings)
    otel_env_lines = _otel_env_lines(otel_env=otel_env)
    codex_steps = _codex_auth_prepare_steps_block(codex_auth_snapshot=codex_auth_snapshot)
    codex_env_lines = _codex_auth_env_lines(codex_auth_snapshot=codex_auth_snapshot)
    return (
        rewritten
        + sibling_steps
        + codex_steps
        + "\n# --- Dispatcher-materialized run-scoped credential projection"
        + "\n# --- (UNCOMMITTED; mode 600; deleted when the run returns) ---\n"
        + f"[environments.{environment_id}.env]\n"
        + f"CLAUDE_CODE_OAUTH_TOKEN = {token_literal}\n"
        + f"GITHUB_TOKEN = {github_token_literal}\n"
        + sibling_env_line
        + core_plugin_env_line
        + currency_gate_env_line
        + otel_env_lines
        + codex_env_lines
    )


def _core_plugin_env_line(*, siblings: SiblingClones | None) -> str:
    """Project LIVESPEC_CORE_PLUGIN_ROOT at the in-sandbox core-sibling clone.

    A fleet repo whose janitor resolves the livespec CORE plugin (the console's
    `check-doctor-static`) cannot find core inside the sandbox: the worker env
    is a fail-closed allowlist and the container carries no installed-plugin
    registry. So the overlay projects CORE's location as a container-level env
    key — the SAME mechanism that carries GITHUB_TOKEN — valued at the cloned core
    sibling's plugin root (`<clones_root>/livespec/.claude-plugin`). Returns the
    empty string when no core sibling is cloned (the derived path would not
    resolve), mirroring the sibling-clones-root guard.
    """
    if siblings is None or _CORE_SIBLING_SLUG not in siblings.repos:
        return ""
    core_plugin_root = f"{siblings.clones_root}/{_CORE_SIBLING_SLUG}/.claude-plugin"
    return f"{CORE_PLUGIN_ROOT_ENV_VAR} = {json.dumps(core_plugin_root)}\n"


def _codex_auth_prepare_steps_block(*, codex_auth_snapshot: str | None) -> str:
    """Render the Codex-auth `[[run.prepare.steps]]` block (Scenario 18).

    Empty string when `codex_auth_snapshot` is None (the Claude-OAuth-only
    shape). The step runs before the agent nodes and writes the projected
    snapshot to `$CODEX_HOME/auth.json` mode-600; both `$CODEX_HOME` and
    `$CODEX_AUTH_JSON` are inherited from the container-level env table the
    same overlay declares, so the shell needs no inline value. The script
    is `json.dumps`-ed to TOML-quote it, matching the sibling-clone steps.
    """
    if codex_auth_snapshot is None:
        return ""
    script = (
        'mkdir -p "$CODEX_HOME" && printf %s "$CODEX_AUTH_JSON" >'
        ' "$CODEX_HOME/auth.json" && chmod 600 "$CODEX_HOME/auth.json"'
    )
    lines = [
        "",
        "# --- Dispatcher-materialized Codex credential projection: write the",
        "# --- non-rotatable auth.json snapshot the codex-acp adapter reads ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(script)}",
    ]
    return "\n".join(lines) + "\n"


def _codex_auth_env_lines(*, codex_auth_snapshot: str | None) -> str:
    """Render the Codex `CODEX_HOME` / `CODEX_AUTH_JSON` env-table lines.

    Empty string when `codex_auth_snapshot` is None. Each value is
    `json.dumps`-ed so the multi-line JSON snapshot single-line-encodes
    with `\\n` escapes (valid TOML), exactly like the CLAUDE_CODE_OAUTH_TOKEN
    / OTel lines. These ride in the same `[environments.<id>.env]` table —
    the container baseline env every sandbox process inherits — so the
    prepare-step shell and the codex-acp child both see them.
    """
    if codex_auth_snapshot is None:
        return ""
    return (
        f"CODEX_HOME = {json.dumps(_SANDBOX_CODEX_HOME)}\n"
        f"CODEX_AUTH_JSON = {json.dumps(codex_auth_snapshot)}\n"
    )


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


def _sibling_clone_steps_block(*, siblings: SiblingClones) -> str:
    """Render the appended sibling-clone `[[run.prepare.steps]]` blocks.

    One step per fleet member (the dispatch target is excluded
    upstream): a depth-1 default-branch `git clone` into
    `<clones_root>/<repo>` — mirroring how livespec CI provisions the
    `LIVESPEC_SIBLING_CLONES_ROOT` siblings-root for the cross-repo
    wiring check. Plain `git clone` over https is used (NOT `gh`): the
    sandbox clones its own workspace repo the same way, while `gh api`
    is unauthenticated there.
    """
    lines: list[str] = [
        "",
        "# --- Dispatcher-materialized sibling clones (from livespec master's",
        "# --- .livespec-fleet-manifest.jsonc): depth-1 default-branch clones so",
        "# --- cross-repo checks resolve every family sibling under",
        f"# --- {siblings.clones_root} inside the sandbox ---",
    ]
    for repo_name in siblings.repos:
        script = (
            f"mkdir -p {siblings.clones_root} && git clone --quiet --depth 1"
            f" https://github.com/{siblings.owner}/{repo_name}.git"
            f" {siblings.clones_root}/{repo_name}"
        )
        lines.append("[[run.prepare.steps]]")
        lines.append(f"script = {json.dumps(script)}")
    return "\n".join(lines) + "\n"
