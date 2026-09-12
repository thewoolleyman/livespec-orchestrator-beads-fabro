"""factory-provenance merge gate — the server-side factory-App authorship wall.

R6a of plan `mechanically-enforce-factory-usage`. This is the MERGE-TIME half
of the pair whose commit-time half is the `Factory-Override` trailer the
factory-bypass audit already counts: a pull request that changes PRODUCT
PYTHON must have been authored by the factory GitHub App, or must carry the
`factory-override` label declaring the exception. Everything else merges
untouched — spec, plan, docs, workflow and config changes are out of scope by
construction, exactly as the Red-Green-Replay scope is.

WHY THIS IS THE HARD WALL. The author identity comes from the forge's own
event payload, so no local marker can forge it; the commit-time trailer stays
spoofable-but-audited. Measured over the last 100 merged pull requests on this
repository (research note 006 of the plan): 69 App-authored, 31
maintainer-authored, and just THREE of those 31 changed product Python. Those
three are the whole population this wall exists for.

WHY THE LOGIN IS CHECKED TWICE. The forge spells the same App two ways: the
webhook payload says `thewoolleyman-factory-bot[bot]`, while `gh` renders it
`app/thewoolleyman-factory-bot`. `auto-enable-merge.yml` already composes a
login gate on the second spelling; accepting only one spelling would turn this
gate into a wall against the factory itself, which is the failure mode that
costs the most and announces itself the least.

WHY A ZERO-PRODUCT-PYTHON DIFF REPORTS VACUITY AND STILL PERMITS THE MERGE.
This is a FILE-SCOPED check: it SELECTS the diff files it judges. Under the
ratified scoped-check vacuity clause (`SPECIFICATION/contracts.md`), a scope
that matched zero files has OBSERVED NOTHING and MUST NOT report a pass — so
the outcome is `vacuous-match`, not `pass`. That is a statement about
EVIDENCE, never about admission: `permits_merge` is True and the exit code is
0, because a pull request carrying no product Python is not blocked on
factory-provenance grounds. Collapsing the two would hide a broken probe
inside a green result, which is how a scoped guard once passed over an empty
diff for four review rounds.

Hermetic in the forge sense: the event payload and the diff, never the ledger.
Wiring this into `ci.yml` and into the `ci-green` aggregate is R6b — a
workflow edit the maintainer lands by hand, because a factory branch never
touches `.github/workflows/`.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_scoped_check_vacuity import (
    ScopedCheckOutcome,
    gate_exit_code,
    gate_tally,
    scoped_check_outcome,
)
from livespec_orchestrator_beads_fabro.commands._factory_bypass_product_paths import (
    ProductPathPolicy,
    is_product_py,
    product_policy,
)
from livespec_orchestrator_beads_fabro.commands._factory_provenance_event import (
    PullRequestEvent,
    diff_range,
    read_changed_paths,
    read_event,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "DEFAULT_RUNNER",
    "FACTORY_APP_LOGINS",
    "FACTORY_OVERRIDE_LABEL",
    "ProvenanceVerdict",
    "decide",
    "exit_code",
    "main",
    "permits_merge",
    "render_verdict",
    "resolve_product_policy",
]

# BOTH spellings the forge uses for the one factory GitHub App. The webhook
# payload emits the `[bot]`-suffixed form; `gh` emits the `app/`-prefixed one.
FACTORY_APP_LOGINS = (
    "app/thewoolleyman-factory-bot",
    "thewoolleyman-factory-bot[bot]",
)
# The declared-exception label. Its REASON belongs in the pull request body,
# where a reviewer and the bypass audit can both read it.
FACTORY_OVERRIDE_LABEL = "factory-override"

DEFAULT_RUNNER: CommandRunner = ShellCommandRunner()

_EXIT_UNOBSERVABLE = 2


@dataclass(frozen=True, slots=True, kw_only=True)
class ProvenanceVerdict:
    """One pull request's factory-provenance outcome, and the evidence behind it."""

    outcome: ScopedCheckOutcome
    author_login: str
    product_paths: tuple[str, ...]
    judged_path_count: int
    factory_authored: bool
    override_labeled: bool


def resolve_product_policy(*, repo: Path) -> ProductPathPolicy:
    """Derive the repository's product-path prefixes from its own declaration."""
    pyproject = repo / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8") if pyproject.is_file() else None
    return product_policy(pyproject_text=text)


def decide(
    *,
    event: PullRequestEvent,
    changed_paths: tuple[str, ...],
    policy: ProductPathPolicy,
) -> ProvenanceVerdict:
    """Decide whether this pull request may merge on factory-provenance grounds."""
    product_paths = tuple(path for path in changed_paths if is_product_py(path=path, policy=policy))
    factory_authored = event.author_login in FACTORY_APP_LOGINS
    override_labeled = FACTORY_OVERRIDE_LABEL in event.labels
    return ProvenanceVerdict(
        outcome=scoped_check_outcome(
            matched_file_count=len(product_paths),
            failing=not factory_authored and not override_labeled,
        ),
        author_login=event.author_login,
        product_paths=product_paths,
        judged_path_count=len(changed_paths),
        factory_authored=factory_authored,
        override_labeled=override_labeled,
    )


def exit_code(*, verdict: ProvenanceVerdict) -> int:
    """The gate's exit code: non-zero ONLY on observed failing provenance evidence."""
    return gate_exit_code(tally=gate_tally(outcomes=(verdict.outcome,)))


def permits_merge(*, verdict: ProvenanceVerdict) -> bool:
    """True iff this verdict leaves the pull request mergeable on provenance grounds."""
    return exit_code(verdict=verdict) == 0


def _routes_out() -> str:
    """The two sanctioned ways past this wall, named in the failure itself."""
    return (
        "Two routes out:\n"
        "1. Dispatch the work item through the factory, so the factory GitHub "
        f"App ({FACTORY_APP_LOGINS[0]}) authors the pull request.\n"
        f"2. Apply the `{FACTORY_OVERRIDE_LABEL}` label and record the reason "
        "for the in-session change in the pull request body."
    )


def render_verdict(*, verdict: ProvenanceVerdict) -> str:
    """The gate's operator-facing message, naming the evidence it judged."""
    if verdict.outcome == "vacuous-match":
        return (
            f"vacuous-match: the product-Python scope matched zero of the "
            f"{verdict.judged_path_count} file(s) in this pull request, so this check "
            "OBSERVED NOTHING. That is not a pass — a gate counts it toward neither "
            "passing nor failing. The pull request is not blocked on factory-provenance "
            "grounds."
        )
    paths = "\n".join(f"- {path}" for path in verdict.product_paths)
    if verdict.outcome == "pass":
        ground = (
            "its author is the factory GitHub App"
            if verdict.factory_authored
            else f"it carries the `{FACTORY_OVERRIDE_LABEL}` label"
        )
        return (
            f"Factory-provenance check: pass — @{verdict.author_login} may change "
            f"product Python because {ground}.\n{paths}"
        )
    return (
        "Factory-provenance check: FAIL — this pull request may not merge.\n\n"
        f"Author: @{verdict.author_login} is not the factory GitHub App, and this "
        f"pull request carries no `{FACTORY_OVERRIDE_LABEL}` label.\n\n"
        f"Product Python it changes:\n{paths}\n\n"
        f"{_routes_out()}"
    )


def _build_parser() -> argparse.ArgumentParser:
    """The CLI surface; `--changed-file` replaces the git diff read for tests."""
    parser = argparse.ArgumentParser(prog="factory-provenance-check")
    _ = parser.add_argument("--event-path", dest="event_path", default=None)
    _ = parser.add_argument("--repo", dest="repo", default=".")
    _ = parser.add_argument("--changed-file", dest="changed_files", action="append", default=None)
    return parser


def _resolve_event_path(*, declared: str | None) -> str | None:
    """The event payload path: the flag, else the Actions environment variable."""
    return declared if declared is not None else os.environ.get("GITHUB_EVENT_PATH")


def main(*, argv: list[str] | None = None, runner: CommandRunner = DEFAULT_RUNNER) -> int:
    """Supervisor for the factory-provenance merge gate. Fails CLOSED, never open."""
    args = _build_parser().parse_args(argv)
    event_path = _resolve_event_path(declared=args.event_path)
    if event_path is None:
        write_stderr(
            text=(
                "factory-provenance check has no event payload to read: pass "
                "--event-path or set GITHUB_EVENT_PATH.\n"
            )
        )
        return _EXIT_UNOBSERVABLE
    event = read_event(path=Path(event_path))
    if event is None:
        write_stderr(
            text=(
                f"factory-provenance check could not read a pull_request event payload "
                f"at {event_path}, so it refuses rather than passing unobserved.\n"
            )
        )
        return _EXIT_UNOBSERVABLE
    repo = Path(args.repo)
    declared_files: list[str] | None = args.changed_files
    changed_paths = (
        tuple(declared_files)
        if declared_files is not None
        else read_changed_paths(event=event, repo=repo, runner=runner)
    )
    if changed_paths is None:
        write_stderr(
            text=(
                f"factory-provenance check could not read the diff for "
                f"{diff_range(event=event)}; a shallow checkout needs "
                "fetch-depth: 0.\n"
            )
        )
        return _EXIT_UNOBSERVABLE
    verdict = decide(
        event=event,
        changed_paths=changed_paths,
        policy=resolve_product_policy(repo=repo),
    )
    message = f"{render_verdict(verdict=verdict)}\n"
    if permits_merge(verdict=verdict):
        write_stdout(text=message)
    else:
        write_stderr(text=message)
    return exit_code(verdict=verdict)
