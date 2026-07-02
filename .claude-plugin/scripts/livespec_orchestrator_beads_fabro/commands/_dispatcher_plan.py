"""Pure planning layer for the Dispatcher: plans, argv builders, parsers.

Everything here is a pure function of its inputs so the hermetic test
tier covers the Dispatcher's decision surface without subprocesses. The
side-effecting execution of these argvs lives in `_dispatcher_engine`
(sequencing) and `_dispatcher_io` (the subprocess seam).

The argv builders encode the Architecture C dispatch discipline
(livespec non-functional-requirements.md + livespec/tmp/fabro-architecture-c-design.md):
`fabro run` executes from the target repo's PRIMARY checkout and Fabro
clones fresh inside its docker sandbox (the host owns no git working
state — no worktree prep, no reaping), the work publishes under
`feat/<work-item-id>` (never the Fabro-managed run-branch name),
`gh pr view` confirms the merge, and the janitor argv is injected from
configuration (never hardcoded).

The run-config helper (`render_run_config_overlay`) materializes the
RUN-SCOPED credential projection (the family-secrets scoped
transient-materialization rule): the committed config carries NO
secret, and the rendered overlay appends an `[environments.<id>.env]`
table carrying the caller-supplied CLAUDE_CODE_OAUTH_TOKEN value (read
from the Dispatcher's process environment) and GH_TOKEN value (a fresh
App installation token minted by the caller's provider — never a fleet
PAT), alongside the `graph`
path rewritten absolute so the overlay resolves from outside the workflow
directory. The same overlay provisions the sandbox sibling clones:
per-fleet-member depth-1 `[[run.prepare.steps]]` clone blocks plus the
non-secret `LIVESPEC_SIBLING_CLONES_ROOT` env key (riding in the same
appended env table — TOML allows only one declaration of that table),
so cross-repo checks under `just check` resolve family siblings inside
the sandbox exactly like livespec CI provisions them.

Fabro `{{ env.* }}` interpolation can NOT carry the
credential for server-mediated runs — do not re-attempt it: the
interpolation resolves in the WORKER process, which fabro-server
spawns with a fail-closed env allowlist (fabro-server/src/spawn_env.rs
— PATH/HOME/TMPDIR/USER/RUST_*/FABRO_*/TERM etc. only), so the token
never reaches the resolver and the LITERAL `{{ env.X }}` string flows
into the sandbox (proven empirically 2026-06-12: API 401 with the
token present in both the dispatcher's and the server daemon's env).
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from livespec_orchestrator_beads_fabro.commands import _jsonc
from livespec_orchestrator_beads_fabro.types import WorkItem

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.store import WorkItemComment

__all__: list[str] = [
    "CODEX_FRESHNESS_MARGIN_SECONDS",
    "CODEX_FRESHNESS_RUN_BUDGET_SECONDS",
    "CODEX_IMPLEMENTER_ADAPTER",
    "CODEX_NON_ROTATABLE_REFRESH_SENTINEL",
    "CORE_PLUGIN_ROOT_ENV_VAR",
    "DEFAULT_SANDBOX_OTEL_ENDPOINT",
    "NON_CONVERGED_MARKER",
    "SANDBOX_OTEL_ENDPOINT_ENV_VAR",
    "SIBLING_CLONES_ROOT_ENV_VAR",
    "CodexFreshnessVerdict",
    "DispatchPlan",
    "FleetMembers",
    "PrView",
    "SiblingClones",
    "assess_codex_credential_freshness",
    "build_plan",
    "cc_otel_overlay_env",
    "escape_minijinja_literal",
    "fabro_events_argv",
    "fabro_inspect_argv",
    "fabro_ps_argv",
    "fabro_rm_argv",
    "fabro_run_argv",
    "host_only_refusal_detail",
    "is_host_only_item",
    "is_non_convergence_outcome",
    "item_sizing_warnings",
    "janitor_argv_with_default",
    "janitor_bootstrap_argv",
    "janitor_checkout_path",
    "janitor_core_checkout_path",
    "janitor_core_clone_argv",
    "janitor_core_ref_from_config",
    "janitor_trust_argv",
    "janitor_worktree_add_argv",
    "janitor_worktree_remove_argv",
    "parse_fleet_members",
    "parse_pr_view",
    "parse_run_id",
    "parse_run_id_for_work_item",
    "parse_run_status",
    "parse_running_run_id",
    "pr_arm_argv",
    "pr_update_branch_argv",
    "pr_view_argv",
    "project_codex_auth_snapshot",
    "pull_primary_argv",
    "render_goal",
    "render_run_config_overlay",
    "resolve_sandbox_otel_endpoint",
]

# The env-var contract shared with livespec's cross-repo doctor checks
# (e.g. `wiring_completeness_cross_repo`): when set, a sibling repo's
# clone resolves as `<value>/<sibling-slug>` instead of the manifest's
# `local_clone` path. livespec CI provisions it the same way; the
# Dispatcher's overlay projects it into the sandbox env table.
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
_CORE_SIBLING_SLUG = "livespec"

# The lever that overrides where the in-sandbox Claude-Code OTel export
# ships (29f.3). It points at the host-local E1 OTLP receiver (29f.7),
# NOT Honeycomb — the sandbox ships PLAINTEXT and the host-local egress
# stage holds the Honeycomb ingest key (telemetry-pipeline-architecture.md
# §3.5). The committed default is the Docker default-bridge gateway:
# inside a fabro docker sandbox `127.0.0.1` is the sandbox's OWN loopback,
# so the host's loopback-bound receiver is reached via the bridge gateway
# address instead. 172.17.0.1 is the conventional Docker default-bridge
# gateway; the orchestrator's later live-verify corrects this lever if the
# real reachable address differs (e.g. `host.docker.internal` when the
# sandbox provisions that alias). NOTE: the host-side E1 receiver defaults
# to a loopback (127.0.0.1) bind — for sandbox egress to actually land it
# must bind a bridge-reachable interface; that host-side wiring is the
# live-verify leg, OUT OF SCOPE for the overlay-assembly here.
SANDBOX_OTEL_ENDPOINT_ENV_VAR = "LIVESPEC_SANDBOX_OTEL_ENDPOINT"
DEFAULT_SANDBOX_OTEL_ENDPOINT = "http://172.17.0.1:4318"

_DEFAULT_JANITOR: tuple[str, ...] = ("mise", "exec", "--", "just", "check")
_DEFAULT_JANITOR_CORE_REPO_URL = "https://github.com/thewoolleyman/livespec.git"
_DEFAULT_JANITOR_CORE_REF = "master"

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_RUN_ID_RE = re.compile(r"Run:\s*([0-9A-Za-z-]+)")

# GitHub owner / repo-name shape. The matched values are spliced into
# prepare-step clone scripts, so anything outside this conservative
# alphabet is refused at parse time (fail-fast over fail-soft: the
# fleet manifest is a tightly-owned committed file on livespec master,
# and a malformed member is a real problem to surface, not skip).
_GITHUB_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

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
class DispatchPlan:
    """Everything one work-item dispatch needs, resolved up front.

    `branch` is the PUBLISH branch (`feat/<work-item-id>`) the phase
    graph's pr stage pushes and the engine polls — the Fabro-managed
    run branch inside the sandbox is run-internal and never leaves it.
    `workflow_toml` is the MATERIALIZED run-config overlay path (the
    committed config plus the credential env table), not the committed
    file itself. `janitor_checkout` is the path the engine provisions
    as a FRESH detached worktree of the merged ref and runs the
    post-merge janitor in — never the host primary's working tree,
    whose environment rot (stale `.venv` shebangs, stale `.coverage`,
    ghost `__pycache__` dirs) once false-redded a confirmed-green
    merge (work-item livespec-impl-beads-cgd).
    """

    repo: Path
    work_item_id: str
    branch: str
    workflow_toml: Path
    goal_file: Path
    fabro_bin: str
    janitor: tuple[str, ...]
    janitor_checkout: Path
    janitor_core_checkout: Path
    janitor_core_repo_url: str
    janitor_core_ref: str


@dataclass(frozen=True, kw_only=True)
class PrView:
    """The slice of `gh pr view --json` the engine routes on."""

    number: int
    state: str
    auto_merge_armed: bool
    merge_state_status: str
    merge_sha: str | None
    terminal_required_check_failures: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class FleetMembers:
    """Owner + member repo names parsed from livespec's .livespec-fleet-manifest.jsonc.

    The fleet manifest (livespec non-functional-requirements.md) is the
    canonical family member registry; the
    `class` field of each member is irrelevant here — every member gets
    a sandbox sibling clone, so any future cross-repo check resolves.
    """

    owner: str
    repos: tuple[str, ...]


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


def parse_fleet_members(*, manifest_text: str) -> FleetMembers | None:
    """Parse .livespec-fleet-manifest.jsonc text into FleetMembers; None when malformed.

    Accepts the committed shape on livespec master: a JSONC object with
    a string `owner` and a non-empty `fleet` list of objects each
    carrying a string `repo`. The livespec v148 rename made `fleet` the
    canonical key; the pre-rename `members` key is accepted as a fallback
    (matching livespec-dev-tooling's `(.fleet // .members)` parser) so a
    not-yet-migrated manifest copy keeps resolving. Owner and repo values
    must be GitHub-slug-shaped (they are spliced into clone scripts). Any
    deviation yields None — the caller refuses the dispatch with an
    actionable error rather than cloning from a guessed member list.
    """
    try:
        parsed_raw: object = _jsonc.loads(text=manifest_text)
    except _jsonc.JsoncParseError:
        return None
    if not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, Any]", parsed_raw)
    owner_raw: object = parsed.get("owner")
    fleet_raw: object = parsed.get("fleet")
    members_raw: object = fleet_raw if fleet_raw is not None else parsed.get("members")
    if not isinstance(owner_raw, str) or not isinstance(members_raw, list):
        return None
    if _GITHUB_SLUG_PATTERN.match(owner_raw) is None:
        return None
    repos: list[str] = []
    for member_raw in cast("list[object]", members_raw):
        repo_name = _parse_member_repo(member_raw=member_raw)
        if repo_name is None:
            return None
        repos.append(repo_name)
    return FleetMembers(owner=owner_raw, repos=tuple(repos)) if repos else None


def _parse_member_repo(*, member_raw: object) -> str | None:
    """Extract a validated repo name from one fleet-manifest member entry."""
    if not isinstance(member_raw, dict):
        return None
    repo_raw: object = cast("dict[str, Any]", member_raw).get("repo")
    if not isinstance(repo_raw, str) or _GITHUB_SLUG_PATTERN.match(repo_raw) is None:
        return None
    return repo_raw


def build_plan(  # noqa: PLR0913 — kw-only plan resolver; each field is an independent caller input.
    *,
    repo: Path,
    work_item_id: str,
    workflow_toml: Path,
    goal_file: Path,
    fabro_bin: str,
    janitor: tuple[str, ...] | None,
    janitor_checkout: Path,
    janitor_core_repo_url: str = _DEFAULT_JANITOR_CORE_REPO_URL,
    janitor_core_ref: str = _DEFAULT_JANITOR_CORE_REF,
) -> DispatchPlan:
    """Resolve the per-item dispatch plan (publish branch, argv config)."""
    return DispatchPlan(
        repo=repo,
        work_item_id=work_item_id,
        branch=f"feat/{work_item_id}",
        workflow_toml=workflow_toml,
        goal_file=goal_file,
        fabro_bin=fabro_bin,
        janitor=janitor_argv_with_default(janitor=janitor),
        janitor_checkout=janitor_checkout,
        janitor_core_checkout=janitor_core_checkout_path(janitor_checkout=janitor_checkout),
        janitor_core_repo_url=janitor_core_repo_url,
        janitor_core_ref=janitor_core_ref,
    )


def janitor_argv_with_default(*, janitor: tuple[str, ...] | None) -> tuple[str, ...]:
    """Return the configured janitor argv, defaulting to `mise exec -- just check`."""
    if janitor is None or len(janitor) == 0:
        return _DEFAULT_JANITOR
    return janitor


def janitor_checkout_path(*, repo: Path, work_item_id: str) -> Path:
    """The post-merge janitor's fresh-checkout venue: `<repo>/worktrees/janitor-<id>`.

    Under the target repo's own `worktrees/` dispatch-worktree dir and
    NEVER under the system temp dir: the family pyproject's
    `[tool.coverage.run]` omit carries `/tmp/*` (a guard against
    measured tempfile artifacts that must stay), so a /tmp venue omits
    every source file inside the checkout — coverage measures zero
    files and check-per-file-coverage dies with NoDataError,
    false-redding a merged-green change (work-item
    livespec-impl-beads-1l6; reproduced in the preserved tpu checkout).
    `git worktree add` creates the missing parent dirs itself.
    """
    return repo / "worktrees" / f"janitor-{work_item_id}"


def janitor_core_checkout_path(*, janitor_checkout: Path) -> Path:
    """Livespec core clone provisioned inside the fresh janitor checkout."""
    return janitor_checkout / ".livespec-core"


def janitor_core_ref_from_config(*, config_text: str) -> str:
    """Resolve the livespec core ref pinned by the target repo config."""
    try:
        parsed_raw: object = _jsonc.loads(text=config_text)
    except _jsonc.JsoncParseError:
        return _DEFAULT_JANITOR_CORE_REF
    if not isinstance(parsed_raw, dict):
        return _DEFAULT_JANITOR_CORE_REF
    parsed = cast("dict[str, object]", parsed_raw)
    plugin_raw: object = parsed.get("livespec-orchestrator-beads-fabro")
    if not isinstance(plugin_raw, dict):
        return _DEFAULT_JANITOR_CORE_REF
    compat_raw: object = cast("dict[str, object]", plugin_raw).get("compat")
    if not isinstance(compat_raw, dict):
        return _DEFAULT_JANITOR_CORE_REF
    pinned_raw: object = cast("dict[str, object]", compat_raw).get("pinned")
    if not isinstance(pinned_raw, str) or pinned_raw.strip() == "":
        return _DEFAULT_JANITOR_CORE_REF
    return pinned_raw.strip()


def render_goal(
    *,
    item: WorkItem,
    repo: Path,
    branch: str,
    comments: tuple[WorkItemComment, ...] = (),
) -> str:
    """Render the per-item brief delivered to the phase graph as the run goal.

    Item specifics ONLY: the durable family discipline (Red-Green-Replay,
    hook rules, PR/merge protocol) lives in the versioned prompt files of
    the phase graph, not here. `comments` are the item's ledger comments
    (operator riders appended after filing — e.g. pre-authorizations);
    they render under a labeled section so they reach the sandbox brief
    (bn4 finding (c): the description-only brief silently dropped them).
    """
    gap_line = f"Gap id: {item.gap_id}\n" if item.gap_id is not None else ""
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
        f"Title: {item.title}\n"
        "\n"
        "Description:\n"
        f"{item.description}\n"
    )
    # Escape AFTER assembly so EVERY interpolated field (title,
    # description, comments, repo path) is neutralized in one place: the
    # whole rendered goal is what flows into fabro's MiniJinja-templated
    # graph `goal` attribute and prompts (work-item livespec-impl-beads-ajv).
    if not comments:
        return escape_minijinja_literal(text=base)
    lines = [
        "",
        "Ledger comments (operator riders appended after filing; treat them as part of the brief):",
    ]
    for index, comment in enumerate(comments, start=1):
        lines.append(f"[{index}] {_comment_entry(comment=comment)}")
    return escape_minijinja_literal(text=base + "\n".join(lines) + "\n")


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


# Sizing heuristics (warn-only; see `item_sizing_warnings`). Calibrated on
# the 2026-06-12 shakedown evidence: the two ACP-turn-timeout casualties
# (dev-tooling p60, git-jsonl tenpup) were both heavy multi-part /
# multi-RGR items with long enumerated descriptions, and both succeeded
# immediately once split out to host sub-agents.
_SIZING_DESCRIPTION_CHAR_LIMIT = 1500
_SIZING_PART_MARKER_RE = re.compile(r"multi[-\s]?(?:part|rgr)", re.IGNORECASE)
_SIZING_ENUMERATED_RE = re.compile(r"\(\d+\)|^\s*\d+[.)]\s", re.MULTILINE)
_SIZING_ENUMERATED_LIMIT = 3

# The explicit host-only routing marker (see `is_host_only_item`). A
# word-bounded `host-only` / `host_only` token: a leading boundary that is
# neither a word char nor a hyphen (so `ghosthost-only` is NOT a match), the
# token with either separator, and a trailing boundary that is neither a word
# char nor a hyphen (so `host-onlyish` is NOT a match).
_HOST_ONLY_MARKER_RE = re.compile(r"(?<![\w-])host[-_]only(?![\w-])", re.IGNORECASE)

# The stable non-convergence sentinel the Fabro workflow-DOT's
# "non-converged" terminal node emits to stderr (work-item
# livespec-impl-beads-rw75ym, Scenario 14) when a slice hits the fix-loop
# cap without converging. The terminal node exits non-zero (no outgoing
# edge), so the run ends non-green and the Dispatcher's engine surfaces
# this marker in the failed outcome's detail; `is_non_convergence_outcome`
# matches it to drive the n5kina bounce-to-`needs-regroom`. Keeping the
# sentinel here makes the DOT-side producer and the Dispatcher-side
# consumer share ONE literal (the DOT references this exact string).
NON_CONVERGED_MARKER = "LIVESPEC_NON_CONVERGED"


def item_sizing_warnings(*, item: WorkItem) -> tuple[str, ...]:
    """Warn-only sizing heuristics applied at dispatch/loop-feed time.

    Pure function of the item; the Dispatcher journals + stderr-WARNs the
    hits and proceeds regardless (never blocking). Three heuristics:
    description length, explicit multi-part/multi-RGR markers, and
    enumerated part counts.
    """
    warnings: list[str] = []
    if len(item.description) > _SIZING_DESCRIPTION_CHAR_LIMIT:
        length_warning = (
            f"description is {len(item.description)} chars "
            f"(> {_SIZING_DESCRIPTION_CHAR_LIMIT}): heavy items have exceeded one "
            "unattended ACP turn; consider splitting before loop-feeding"
        )
        warnings.append(length_warning)
    if _SIZING_PART_MARKER_RE.search(f"{item.title}\n{item.description}") is not None:
        marker_warning = (
            "title/description carries a multi-part/multi-RGR marker: such items "
            "have exceeded one unattended ACP turn; consider splitting"
        )
        warnings.append(marker_warning)
    enumerated = len(_SIZING_ENUMERATED_RE.findall(item.description))
    if enumerated >= _SIZING_ENUMERATED_LIMIT:
        enumerated_warning = (
            f"description carries {enumerated} enumerated parts: consider one "
            "work-item per part before loop-feeding"
        )
        warnings.append(enumerated_warning)
    return tuple(warnings)


def is_host_only_item(*, item: WorkItem) -> bool:
    """Recognise the explicit host-only routing marker on a work-item.

    Mechanizes the currently-manual routing rule (judgment-leaning OR
    touches dispatcher self-machinery -> host sub-agent; ddu rationale)
    AND prevents the proven 7us.6 hang class: a commit-hook
    self-machinery item mis-routed to a fabro sandbox once deadlocked the
    in-sandbox `git commit` (a 2.5h silent stall; work-item
    livespec-impl-beads-uvd). The Dispatcher reads this predicate BEFORE
    launching any fabro run and refuses to sandbox a host-only item.

    The marker is the EXPLICIT contract — a `host-only` / `host_only`
    token in the item's title or description — carried in the only
    field-space the `WorkItem` schema exposes without a cross-repo
    contracts.md change (the mapped beads record drops unrecognised
    labels). It is recognised exactly the way `item_sizing_warnings`
    recognises its `multi-part/multi-RGR` marker, but as a HARD refuse
    rather than a warn. The token is word-bounded so incidental prose
    like "the host is only sometimes ready" never trips the gate.
    """
    return _HOST_ONLY_MARKER_RE.search(f"{item.title}\n{item.description}") is not None


def host_only_refusal_detail(*, item_id: str) -> str:
    """Build the actionable refusal message for a sandboxed host-only item.

    Routed as DATA (the `host-only-refused` DispatchOutcome detail), so
    the orchestrator reads a clear instruction to HOST-ROUTE the item to
    a host sub-agent instead of retrying the sandbox — never a launched
    run, so the in-sandbox/in-hook `git commit` can never deadlock.
    """
    return (
        f"host-only refusal: work-item {item_id} carries the explicit host-only "
        "marker and MUST NOT be dispatched to a fabro sandbox (sandboxing "
        "dispatcher self-machinery once deadlocked the in-sandbox git commit — "
        "the 7us.6 hang class). Host-route it to a host sub-agent instead "
        "(the livespec-implementer dispatch path)."
    )


class _NonConvergenceOutcome(Protocol):
    """Structural view of a terminal outcome's non-convergence signals.

    The pure planning layer cannot import `DispatchOutcome` from
    `_dispatcher_engine` (that module imports THIS one — a concrete import
    would be circular), so the predicate reads only the two fields it
    needs through this Protocol. `DispatchOutcome` satisfies it
    structurally, so the Dispatcher passes the dataclass straight through.
    """

    @property
    def status(self) -> str: ...

    @property
    def detail(self) -> str: ...


def is_non_convergence_outcome(*, outcome: _NonConvergenceOutcome) -> bool:
    """Recognise a non-convergence terminal the Dispatcher must bounce (n5kina).

    Per SPECIFICATION/contracts.md and
    SPECIFICATION/scenarios.md "Scenario 11 — Dispatcher bounces a
    non-converging slice to needs-regroom": a dispatched slice that will
    not converge through the janitor gate within the bounded fix-loop cap
    MUST be marked `needs-regroom` and surfaced, never infinite-retried.
    The Dispatcher reads this predicate AFTER the terminal outcome to
    decide whether to bounce the item to `needs-regroom`.

    Two mechanical signals mark non-convergence, both already produced by
    the existing dispatch path:

    - `stalled-no-progress` — the coarse wall-clock watchdog confirmed the
      run made no progress for the full stall window and `fabro rm -f`-ed
      it (the 7us.6 hang class). A stalled run will not converge and would
      otherwise be retried; it is the empirical non-convergence terminal
      already in the engine's vocabulary.
    - the DOT non-converged sentinel — the single Fabro workflow-DOT tweak
      (work-item livespec-impl-beads-rw75ym, Scenario 14) routes a
      fix-loop-cap exhaustion to a terminal `non_converged` node that exits
      non-zero with `NON_CONVERGED_MARKER` on stderr. The run ends non-green
      and the engine surfaces that marker in the failed outcome's `detail`,
      so a substring match recovers the DOT's non-converged exit edge as a
      Dispatcher-side bounce trigger.

    Ordinary failures (a `host-only-refused` / `human-gated-surfaced`
    routing refusal, a `blocked` human-gate park, a one-off `pr-view`
    failure) are NOT non-convergence and must not be bounced, so the match
    is deliberately narrow — the watchdog status plus the explicit DOT
    sentinel only.
    """
    if outcome.status == "stalled-no-progress":
        return True
    return outcome.status == "failed" and NON_CONVERGED_MARKER in outcome.detail


def resolve_sandbox_otel_endpoint(*, environ: dict[str, str]) -> str:
    """Resolve the sandbox->host OTLP endpoint for in-sandbox CC OTel (29f.3).

    The in-sandbox Claude-Code OTel export ships PLAINTEXT OTLP to the
    host-local E1 receiver (29f.7), NOT Honeycomb — the Honeycomb ingest
    key stays on the host-local egress stage (telemetry design §3.5). This
    endpoint is the host *as reachable from inside the fabro docker
    sandbox*: inside the container `127.0.0.1` is the sandbox's OWN
    loopback, so the host's loopback-bound receiver is reached via the
    Docker bridge gateway instead.

    The `LIVESPEC_SANDBOX_OTEL_ENDPOINT` lever overrides the committed
    default (`http://172.17.0.1:4318`, the conventional Docker
    default-bridge gateway on the OTLP/HTTP port). The default is a
    best-determined address — fabro's binary does not auto-provision a
    `host.docker.internal` alias, so the bridge-gateway IP is the
    reliable default; the orchestrator's later live-verify corrects this
    lever if the real reachable address differs. A blank / whitespace-only
    override falls back to the default rather than shipping an empty
    endpoint (the same fail-soft discipline as the cost-cap / receiver
    levers).
    """
    override = environ.get(SANDBOX_OTEL_ENDPOINT_ENV_VAR, "").strip()
    return override or DEFAULT_SANDBOX_OTEL_ENDPOINT


def cc_otel_overlay_env(
    *,
    work_item_id: str,
    dispatch_id: str,
    endpoint: str,
) -> dict[str, str]:
    """Assemble the in-sandbox Claude-Code OTel env dict (29f.3).

    Pure function of the dispatch context (work-item id, dispatch id,
    resolved sandbox->host endpoint). Returns the exact env the run-config
    overlay projects into the sandbox so CC exports native telemetry to
    the host-local E1 receiver. Built from the 29f.1 gap analysis
    (cc-otel-gap-analysis.md §4) and the telemetry pipeline design
    (§3.3 correlation triple, §3.4 content-flags-off, §3.5 plaintext to
    the host-local stage):

    - **Enable + native signals**: the master switch plus all three
      signals on OTLP — metrics, logs (CC events ride the logs signal),
      and the BETA trace exporter (`CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`;
      harmless if the beta is org-gated — metrics + events still deliver).
    - **Transport**: the host-local E1 receiver, `http/json` (the 29f.7
      receiver is JSON-only), base URL only (CC appends the per-signal
      `/v1/<signal>` path). No `OTEL_EXPORTER_OTLP_HEADERS` / ingest key —
      the sandbox ships plaintext; the key lives on the host egress stage.
    - **Correlation triple** (§3.3): `OTEL_RESOURCE_ATTRIBUTES` carries
      `work.item.id` + `livespec.dispatch.id` (the dispatcher knows both
      at dispatch time) plus `service.namespace=livespec-family`, so every
      CC metric / event / span lands pre-joined to the dispatch.
      `service.name` is left at CC's own `claude-code` (one dataset for
      all sandbox CC telemetry, sliced by `work.item.id`).
    - **Short metric interval** (10s): a short-lived sandbox would
      otherwise lose the tail; the metrics-heartbeat also feeds 29f.6's
      oyg `LivenessProbe`.
    - **Content flags**: ALL four CC content-bearing flags
      (`OTEL_LOG_USER_PROMPTS` / `_TOOL_DETAILS` / `_TOOL_CONTENT` /
      `_RAW_API_BODIES`) are deliberately UNSET so CC redacts prompts /
      tool I/O / raw API bodies at the source (§3.4 credential hygiene).
    """
    resource_attributes = ",".join(
        (
            "service.namespace=livespec-family",
            f"work.item.id={work_item_id}",
            f"livespec.dispatch.id={dispatch_id}",
        )
    )
    return {
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_TRACES_EXPORTER": "otlp",
        "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
        "OTEL_EXPORTER_OTLP_ENDPOINT": endpoint,
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
        "OTEL_RESOURCE_ATTRIBUTES": resource_attributes,
        "OTEL_METRIC_EXPORT_INTERVAL": "10000",
        "OTEL_LOGS_EXPORT_INTERVAL": "5000",
    }


CODEX_NON_ROTATABLE_REFRESH_SENTINEL = "livespec-orch-no-refresh-sentinel"

# The sandbox path the projected Codex auth.json is written to. The
# prepare step (running before the agent nodes) writes the credential
# here, and the codex-acp child reads it via $CODEX_HOME — both inherit
# CODEX_HOME from the container-level [environments.<id>.env] table.
_SANDBOX_CODEX_HOME = "/workspace/.codex"

# The Codex ACP adapter the implementer nodes (implement/fix/pr/review_fix)
# run on. PINNED to @0.16.0 — the version where the non-rotatable refresh
# sentinel's load-but-cannot-refresh behavior (project_codex_auth_snapshot)
# was empirically verified against codex-core's AuthManager. Bumping the
# pin requires re-verifying that the sentinel still degrades to a cached
# access-token fall-back rather than failing the load (tracked by
# bd-ib-ss7rkr); a silent bump could break credential projection.
CODEX_IMPLEMENTER_ADAPTER = "npx -y @zed-industries/codex-acp@0.16.0"


def project_codex_auth_snapshot(*, source_auth_json: str) -> str:
    """Project a non-rotatable Codex credential snapshot (pure string transform).

    Realizes the `Worker credential projection` contract (scenarios.md
    "Scenario 18 — Dispatcher projects a non-rotatable subscription
    credential into a worker sandbox"): given the host's live
    ChatGPT-subscription `auth.json` text, return the snapshot to write
    into the worker sandbox's `CODEX_HOME/auth.json` with
    `tokens.refresh_token` REPLACED by an inert sentinel. The worker runs
    on the multi-day access token and cannot rotate the shared refresh
    credential, so no worker can invalidate the host's or a peer worker's
    credential. Every other field (`access_token`, `id_token`,
    `account_id`, `auth_mode`, ...) is preserved so codex-core
    authenticates normally.

    codex-core requires `tokens.refresh_token` to be a present, non-null
    string -- a stripped key or JSON null fails to load -- so the sentinel
    keeps the credential loadable while being unusable for a real refresh,
    which codex-core's AuthManager degrades to a fall-back on the cached
    access token.
    """
    source: dict[str, Any] = json.loads(source_auth_json)
    raw_tokens = source.get("tokens")
    tokens: dict[str, Any] = (
        dict(cast("dict[str, Any]", raw_tokens)) if isinstance(raw_tokens, dict) else {}
    )
    tokens["refresh_token"] = CODEX_NON_ROTATABLE_REFRESH_SENTINEL
    projected: dict[str, Any] = {**source, "tokens": tokens}
    return json.dumps(projected, indent=2, sort_keys=True) + "\n"


CODEX_FRESHNESS_MARGIN_SECONDS = 3600

# The freshness gate's run budget: the realistic maximum wall-clock a single
# dispatch can run. The gate requires the projected Codex credential to outlive
# this budget plus CODEX_FRESHNESS_MARGIN_SECONDS before dispatch (Scenario 19).
#
# Anchored to the Fabro `implement` node's per-turn ceiling
# (.fabro/workflows/implement-work-item/workflow.fabro, timeout="14400s" = 4h):
# implement is the dominant leg of a run, while the downstream janitor/review/pr
# nodes are sub-hour ceilings that realistically take minutes, comfortably
# absorbed by the 1h margin. Observed real dispatches run ~30-45min, so 4h
# carries ~5-8x slack; the gate thus requires the token to outlive 5h total.
#
# DELIBERATELY DECOUPLED from `_dispatcher_engine._FABRO_TIMEOUT_SECONDS`
# (54000s = 15h). That 15h value is a coarse subprocess CEILING / defense-in-depth
# backstop, NOT an expected run length; wiring it in as the freshness run budget
# demanded the token outlive 15h + 1h = 16h, so a host Codex token (minted ~18h,
# dropping below 16h within ~2h) was refused for nearly every unattended dispatch.
CODEX_FRESHNESS_RUN_BUDGET_SECONDS = 14400


@dataclass(frozen=True, kw_only=True)
class CodexFreshnessVerdict:
    """Outcome of the dispatch-time Codex credential freshness gate."""

    fresh_enough: bool
    access_token_expires_at_epoch: int
    renewal_message: str | None


def assess_codex_credential_freshness(
    *,
    source_auth_json: str,
    now_epoch: int,
    run_budget_seconds: int,
) -> CodexFreshnessVerdict:
    """Decide whether the host Codex credential outlives the worker run budget.

    Realizes the `Worker credential projection` freshness gate (scenarios.md
    "Scenario 19 — Dispatcher refuses dispatch when the credential freshness
    gate fails"): decode the ChatGPT-subscription access token's `exp` claim
    and require it to stay valid for the full run budget plus a safety
    margin. When it does not, the Dispatcher MUST refuse the dispatch and
    surface the renewal message instead of projecting a credential that may
    expire mid-run.
    """
    expires_at = _decode_codex_access_token_exp(source_auth_json=source_auth_json)
    required_remaining = run_budget_seconds + CODEX_FRESHNESS_MARGIN_SECONDS
    fresh_enough = (expires_at - now_epoch) >= required_remaining
    renewal_message = (
        None
        if fresh_enough
        else (
            "Host Codex credential is too short-lived for the run budget; "
            "run `codex login` on the orchestrator host to renew it."
        )
    )
    return CodexFreshnessVerdict(
        fresh_enough=fresh_enough,
        access_token_expires_at_epoch=expires_at,
        renewal_message=renewal_message,
    )


def _decode_codex_access_token_exp(*, source_auth_json: str) -> int:
    source: dict[str, Any] = json.loads(source_auth_json)
    raw_tokens = source.get("tokens")
    tokens: dict[str, Any] = (
        cast("dict[str, Any]", raw_tokens) if isinstance(raw_tokens, dict) else {}
    )
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str):
        raise ValueError("auth.json tokens.access_token is missing or not a string")  # noqa: TRY003, TRY004
    segments = access_token.split(".")
    if len(segments) < 2:  # noqa: PLR2004
        raise ValueError("access token is not a JWT")  # noqa: TRY003
    padded = segments[1] + "=" * (-len(segments[1]) % 4)
    claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(padded))
    exp = claims.get("exp")
    if not isinstance(exp, int):
        raise ValueError("access token has no integer exp claim")  # noqa: TRY003, TRY004
    return exp


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
    """Render the dispatch-time run-config overlay (pure string transform).

    The overlay is the RUN-SCOPED credential projection (per the
    family-secrets scoped transient-materialization rule): the committed
    config with (a) the `[workflow]` graph path rewritten to an absolute
    path (the materialized file lives outside the workflow directory, so
    a relative graph would not resolve), (b) appended sibling-clone
    `[[run.prepare.steps]]` blocks (when `siblings` is not None) so
    cross-repo checks resolve family siblings inside the sandbox, and
    (c) an appended `[environments.<id>.env]` table carrying the
    caller-supplied CLAUDE_CODE_OAUTH_TOKEN (read from the Dispatcher's
    process environment) and GH_TOKEN (a freshly minted App installation
    token) plus the NON-secret `LIVESPEC_SIBLING_CLONES_ROOT` key.
    The non-secret key rides in the credential table because TOML
    forbids a second declaration of the same table and this appended
    table is the single `[environments.<id>.env]` declaration point —
    the committed file deliberately carries none; the table maps to
    docker container-level env (fabro-sandbox), so the value reaches
    every node's `just check` subprocesses.

    When `otel_env` is not None (the 29f.3 in-sandbox CC OTel projection),
    its key/value pairs are appended to that SAME
    `[environments.<id>.env]` table (sorted for a stable overlay), turning
    on Claude-Code native telemetry inside the sandbox pointed at the
    host-local E1 receiver. The keys ride in the credential table for the
    same TOML reason the sibling-clones key does — that table is the
    single declaration point. These values are NON-secret (endpoint, env
    knobs, the correlation triple); the Honeycomb ingest key is NOT among
    them (the sandbox ships plaintext; the host egress stage holds the
    key). Omitting `otel_env` preserves the pre-29f.3 token-only shape.

    When `codex_auth_snapshot` is not None (the dual-credential
    projection, scenarios.md Scenario 18), the overlay ALSO gains (a) an
    extra `[[run.prepare.steps]]` block that writes the snapshot to
    `$CODEX_HOME/auth.json` mode-600 before the agent nodes start, and
    (b) two extra `[environments.<id>.env]` lines — `CODEX_HOME` and
    `CODEX_AUTH_JSON`. The container-level env table is the baseline env
    for EVERY process in the sandbox, so the prepare-step shell AND the
    codex-acp child both inherit `CODEX_HOME`/`CODEX_AUTH_JSON`; the
    prepare step (running before the agent nodes) materializes the file
    the adapter reads. The snapshot is non-rotatable
    (`project_codex_auth_snapshot` replaced the refresh token with the
    inert sentinel upstream), so a worker cannot rotate the shared
    credential. Omitting `codex_auth_snapshot` keeps the overlay
    byte-identical to the Claude-OAuth-only shape.

    The committed file itself carries NO secret and NO `{{ env }}`
    interpolation — interpolation cannot deliver the credential to
    server-mediated runs, because the server spawns the resolving
    worker with a fail-closed env allowlist
    (fabro-server/src/spawn_env.rs); see the module docstring. The
    caller writes the rendered text mode-600 and deletes it when the
    run returns. Returns None when the committed shape is unusable (no
    canonical graph value or no run-environment id).
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
        + f"GH_TOKEN = {github_token_literal}\n"
        + sibling_env_line
        + core_plugin_env_line
        + otel_env_lines
        + codex_env_lines
    )


def _core_plugin_env_line(*, siblings: SiblingClones | None) -> str:
    """Project LIVESPEC_CORE_PLUGIN_ROOT at the in-sandbox core-sibling clone.

    A fleet repo whose janitor resolves the livespec CORE plugin (the console's
    `check-doctor-static`) cannot find core inside the sandbox: the worker env
    is a fail-closed allowlist and the container carries no installed-plugin
    registry. So the overlay projects CORE's location as a container-level env
    key — the SAME mechanism that carries GH_TOKEN — valued at the cloned core
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


def fabro_run_argv(*, plan: DispatchPlan) -> list[str]:
    # `--input acp_adapter=...` statically routes the implementer nodes
    # (implement/fix/pr/review_fix) to the Codex ACP adapter; the review
    # node uses its own `review_adapter` default (Slice A) and is
    # unaffected. The dual-credential overlay projects the matching
    # auth.json so the adapter authenticates from the host snapshot.
    return [
        plan.fabro_bin,
        "run",
        str(plan.workflow_toml),
        "--goal-file",
        str(plan.goal_file),
        "--input",
        f"acp_adapter={CODEX_IMPLEMENTER_ADAPTER}",
        "--no-upgrade-check",
    ]


def fabro_inspect_argv(*, plan: DispatchPlan, run_id: str) -> list[str]:
    return [plan.fabro_bin, "inspect", run_id, "--json"]


def fabro_events_argv(*, plan: DispatchPlan, run_id: str) -> list[str]:
    """`fabro events <run-id> --json`: the per-run event log (liveness source).

    The watchdog reads the maximum event timestamp here as its coarse
    liveness signal (work-item livespec-impl-beads-oyg); a stream that
    flatlines for the full stall window is the confirmed-stall signal.
    """
    return [plan.fabro_bin, "events", run_id, "--json"]


def fabro_ps_argv(*, plan: DispatchPlan) -> list[str]:
    """`fabro ps -a --json`: per-run metadata used to discover the run id.

    The watchdog cannot read the run id from the still-blocking `fabro
    run` output, so it discovers the in-flight run for this dispatch from
    `fabro ps` (matched on the work-item id embedded in the run's goal
    text plus a `running` status — see `parse_running_run_id`).
    """
    return [plan.fabro_bin, "ps", "-a", "--json"]


def fabro_rm_argv(*, plan: DispatchPlan, run_id: str) -> list[str]:
    """`fabro rm -f <run-id>`: force-cancel a confirmed-stalled run.

    The watchdog calls this on a confirmed sustained-no-progress stall to
    free the slot + stop the spend (the manual `fabro rm` a human had to
    do at 152min in the 7us.6 incident, now mechanized).
    """
    return [plan.fabro_bin, "rm", "-f", run_id]


def parse_running_run_id(*, ps_json: str, work_item_id: str) -> str | None:
    """Find the RUNNING run id for `work_item_id` from `fabro ps -a --json`.

    `fabro ps -a --json` lists per-run metadata: a `run_id`, a
    serde-tagged `status` (`{"kind": "running", ...}` or a plain string),
    and the full `goal` text (which embeds `Work-item: <id>` per
    `render_goal`). The watchdog matches the run whose goal contains this
    dispatch's work-item id AND whose status is `running` — the in-flight
    run to watch. None when no such run is found yet (the run may not have
    registered; the watchdog treats that as "no signal", never a stall).
    Accepts a top-level array or a `{"runs": [...]}` envelope.
    """
    try:
        parsed_raw: object = json.loads(ps_json)
    except json.JSONDecodeError:
        return None
    runs = _runs_list(parsed_raw=parsed_raw)
    for run_raw in runs:
        run_id = _running_run_id_for(run_raw=run_raw, work_item_id=work_item_id)
        if run_id is not None:
            return run_id
    return None


def _runs_list(*, parsed_raw: object) -> list[object]:
    """Normalize `fabro ps --json` to a list (top-level array or {"runs": [...]})."""
    if isinstance(parsed_raw, list):
        return cast("list[object]", parsed_raw)
    if isinstance(parsed_raw, dict):
        runs_raw: object = cast("dict[str, Any]", parsed_raw).get("runs")
        if isinstance(runs_raw, list):
            return cast("list[object]", runs_raw)
    return []


def parse_run_id_for_work_item(*, ps_json: str, work_item_id: str) -> str | None:
    """Find the run id for `work_item_id` from `fabro ps -a --json`, any status.

    Like `parse_running_run_id` but STATUS-AGNOSTIC: it matches the run
    whose goal embeds `work_item_id` regardless of status, which is what
    the post-dispatch cost gate needs — the run is terminal (succeeded /
    failed) by the time the cost is read, not `running`. The cost source
    (work-item livespec-impl-beads-5v9) is `fabro ps -a --json`'s
    `total_usd_micros`, keyed by this run id. None when no goal embeds the
    id or the JSON is unusable; the cost gate journals `cost-gate-skipped`
    for a None match rather than crashing the wave.
    """
    try:
        parsed_raw: object = json.loads(ps_json)
    except json.JSONDecodeError:
        return None
    for run_raw in _runs_list(parsed_raw=parsed_raw):
        if not isinstance(run_raw, dict):
            continue
        run = cast("dict[str, Any]", run_raw)
        goal_raw: object = run.get("goal")
        if not isinstance(goal_raw, str) or work_item_id not in goal_raw:
            continue
        run_id_raw: object = run.get("run_id")
        if isinstance(run_id_raw, str) and run_id_raw:
            return run_id_raw
    return None


def _running_run_id_for(*, run_raw: object, work_item_id: str) -> str | None:
    """Return the run id IFF this entry is a running run for `work_item_id`."""
    if not isinstance(run_raw, dict):
        return None
    run = cast("dict[str, Any]", run_raw)
    goal_raw: object = run.get("goal")
    if not isinstance(goal_raw, str) or work_item_id not in goal_raw:
        return None
    if _run_status_kind(run=run) != "running":
        return None
    run_id_raw: object = run.get("run_id")
    return run_id_raw if isinstance(run_id_raw, str) and run_id_raw else None


def _run_status_kind(*, run: dict[str, Any]) -> str | None:
    """Read a run entry's status kind (`{"kind": ...}` or a plain string)."""
    status_raw: object = run.get("status")
    if isinstance(status_raw, str):
        return status_raw
    if isinstance(status_raw, dict):
        kind_raw: object = cast("dict[str, Any]", status_raw).get("kind")
        if isinstance(kind_raw, str):
            return kind_raw
    return None


def pr_view_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        "gh",
        "pr",
        "view",
        plan.branch,
        "--json",
        "number,state,autoMergeRequest,mergeStateStatus,mergeCommit,statusCheckRollup",
    ]


def pr_arm_argv(*, plan: DispatchPlan, number: int) -> list[str]:
    _ = plan
    return ["gh", "pr", "merge", str(number), "--rebase", "--auto", "--delete-branch"]


def pr_update_branch_argv(*, plan: DispatchPlan, number: int) -> list[str]:
    _ = plan
    return ["gh", "pr", "update-branch", str(number)]


def pull_primary_argv(*, plan: DispatchPlan) -> list[str]:
    return [
        "mise",
        "exec",
        "--",
        "git",
        "-C",
        str(plan.repo),
        "pull",
        "--ff-only",
        "origin",
        "master",
    ]


def janitor_worktree_add_argv(*, plan: DispatchPlan, ref: str) -> list[str]:
    """Provision the fresh detached janitor checkout at the merged ref.

    Plain `git` (no `mise exec`): worktree commands fire no hooks and
    need no pinned toolchain, and the checkout path is not yet
    mise-trusted at this point anyway.
    """
    return [
        "git",
        "-C",
        str(plan.repo),
        "worktree",
        "add",
        "--detach",
        str(plan.janitor_checkout),
        ref,
    ]


def janitor_worktree_remove_argv(*, plan: DispatchPlan) -> list[str]:
    """Remove the janitor checkout (both pre-clean and post-green cleanup).

    `--force` covers the untracked state a janitor run leaves behind
    (the self-provisioned `.venv`), and as the pre-clean it also clears
    a stale registration left by a crashed earlier dispatch of the same
    item.
    """
    return [
        "git",
        "-C",
        str(plan.repo),
        "worktree",
        "remove",
        "--force",
        str(plan.janitor_checkout),
    ]


def janitor_core_clone_argv(*, plan: DispatchPlan) -> list[str]:
    """Clone livespec core inside the fresh janitor checkout."""
    return [
        "git",
        "clone",
        "--quiet",
        "--depth",
        "1",
        "--branch",
        plan.janitor_core_ref,
        plan.janitor_core_repo_url,
        str(plan.janitor_core_checkout),
    ]


def janitor_trust_argv() -> list[str]:
    """Trust the janitor checkout's mise config (run with cwd=checkout).

    mise trust is per-PATH, so a freshly provisioned checkout is never
    pre-trusted and the default janitor's `mise exec` would refuse to
    run there. With no config file present, `mise trust` warns and
    exits 0, so this is safe to run unconditionally.
    """
    return ["mise", "trust"]


def janitor_bootstrap_argv() -> list[str]:
    """Install canonical commit-refuse hooks in the primary checkout (run with cwd=plan.repo).

    Runs the hooks-only bootstrap recipe in the primary checkout so
    the canonical pre-commit and pre-push hooks are present at
    `.git/hooks/` before `just check` runs in the janitor worktree - the shared
    `check-primary-checkout-commit-refuse-hook-installed` gate reads
    the same hooks_dir and fails when the bootstrap step was never run.
    Idempotent: safe to run on every dispatch.
    """
    return ["mise", "exec", "--", "just", "install-commit-refuse-hooks"]


def parse_run_id(*, output: str) -> str | None:
    """Extract the run id from `fabro run` CLI output.

    The CLI prints `Run: <run-id>` (possibly ANSI-dimmed) when a run
    starts; None when no such line is present (e.g. fabro crashed
    before allocating a run).
    """
    plain = _ANSI_ESCAPE_RE.sub("", output)
    match = _RUN_ID_RE.search(plain)
    if match is None:
        return None
    return match.group(1)


def parse_run_status(*, stdout: str) -> str | None:
    """Parse the status kind out of `fabro inspect <run-id> --json`.

    The status field is a serde-tagged union (`{"kind": "blocked", ...}`
    in fabro v0.254.0); a plain string status is accepted for
    forward-compatibility. None when the shape is unusable.
    """
    try:
        parsed_raw: object = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, Any]", parsed_raw)
    status_raw: object = parsed.get("status")
    if isinstance(status_raw, str):
        return status_raw
    if isinstance(status_raw, dict):
        kind_raw: object = cast("dict[str, Any]", status_raw).get("kind")
        if isinstance(kind_raw, str):
            return kind_raw
    return None


def parse_pr_view(*, stdout: str) -> PrView | None:
    """Parse `gh pr view --json` output; None when the shape is unusable."""
    try:
        parsed_raw: object = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed_raw, dict):
        return None
    parsed = cast("dict[str, Any]", parsed_raw)
    number_raw: object = parsed.get("number")
    if not isinstance(number_raw, int):
        return None
    state_raw: object = parsed.get("state")
    state = state_raw if isinstance(state_raw, str) else "UNKNOWN"
    merge_state_raw: object = parsed.get("mergeStateStatus")
    merge_state = merge_state_raw if isinstance(merge_state_raw, str) else "UNKNOWN"
    terminal_failures: list[str] = []
    rollup_raw: object = parsed.get("statusCheckRollup")
    if isinstance(rollup_raw, list):
        rollup_items_raw = cast("list[object]", rollup_raw)
        rollup_items = [
            cast("dict[str, Any]", item_raw)
            for item_raw in rollup_items_raw
            if isinstance(item_raw, dict)
        ]
        for item in rollup_items:
            if item.get("required") is not True and item.get("isRequired") is not True:
                continue
            conclusion_raw: object = item.get("conclusion")
            if not isinstance(conclusion_raw, str):
                continue
            if conclusion_raw.lower() not in {
                "failure",
                "cancelled",
                "timed_out",
                "action_required",
                "startup_failure",
            }:
                continue
            name_raw: object = item.get("name", item.get("context"))
            terminal_failures.append(
                name_raw if isinstance(name_raw, str) and name_raw else "unknown"
            )
    return PrView(
        number=number_raw,
        state=state,
        auto_merge_armed=parsed.get("autoMergeRequest") is not None,
        merge_state_status=merge_state,
        merge_sha=_merge_sha_of(parsed=parsed),
        terminal_required_check_failures=tuple(terminal_failures),
    )


def _merge_sha_of(*, parsed: dict[str, Any]) -> str | None:
    commit_raw: object = parsed.get("mergeCommit")
    if not isinstance(commit_raw, dict):
        return None
    commit = cast("dict[str, Any]", commit_raw)
    oid_raw: object = commit.get("oid")
    if isinstance(oid_raw, str) and oid_raw:
        return oid_raw
    return None


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
