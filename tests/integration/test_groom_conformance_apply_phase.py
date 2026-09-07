"""The groom variant's conformance gate, driven for BOTH phases against its own script.

Work-item `bd-ib-xea2rq`: the gate's script once short-circuited the apply phase
with a bare `exit 0`, so an apply run that produced no filing plan passed
conformance VACUOUSLY and the omission surfaced one node later — in the review
turn, on a paid model, ending at `needs_human`. The short-circuit is gone: it
was removed by `bde1dbd6` while the apply phase was being moved to host-side
filing, which is a different change that happened to close it. Nothing ever
PROVED it gone. No test in this repository drove the groom conformance node at
all, for either phase, so the guarantee was a side effect of another commit
rather than a pinned one, and the next edit to that script could reinstate the
short-circuit with every check still green. This module pins it.

EVERY BEHAVIOURAL CASE RUNS THE NODE'S OWN SCRIPT, extracted from the graph the
production registry resolves and unescaped, never a paraphrase — the same
discipline `test_workflow_needs_human_terminal_scenario103.py` applies to the
bundle's terminal node. Two substitutions are made on that text, and each is
asserted to have APPLIED, because a substitution that silently matched nothing
would leave the case running against something other than what it claims:

  - the `default_branch` input token is rendered to the fixture repository's
    branch, because a script node reaches its shell already rendered; and
  - the `/tmp/livespec-groom-` scratch prefix is re-rooted into `tmp_path`, so a
    test run cannot collide with a concurrent test run — or with a LIVE groom
    run, which shares the same real `/tmp` on this host.

The production text is asserted to name the real `/tmp` paths BEFORE that
re-rooting, so the substitution cannot hide a drift between the path this gate
checks, the path `prompts/implement.md` writes, and the path the review node
reads. Those three agreeing is the whole point of the gate.

"Before any review turn" is asserted on two instruments, because neither one
carries it alone: the script EXITS NON-ZERO on a missing plan, and the graph's
only edge from `conformance` to `review` is conditioned on that node having
succeeded, so a non-zero exit routes to `fix` or to the non-converged terminal
and no review turn is ever spent.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _config
from livespec_orchestrator_beads_fabro.commands._config import resolve_workflow_variant
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml

# `commands/_config.py` sits at `.claude-plugin/scripts/<package>/commands/`, so
# the repository root is four directories above it. Derived from the imported
# module rather than from this test file's own location, so the anchor cannot
# drift if the test tree is reshaped.
_REPO_ROOT = Path(_config.__file__).resolve().parents[4]
_GROOM_VARIANT_NAME = "groom-work-item"

_SENTINEL = "LIVESPEC_GROOM_MALFORMED"
# The scratch paths as the SHIPPED script spells them, before any re-rooting.
_SCRATCH_PREFIX = "/tmp/livespec-groom-"
_PHASE_PATH = f"{_SCRATCH_PREFIX}phase"
_DRAFT_PATH = f"{_SCRATCH_PREFIX}draft"
_PLAN_PATH = f"{_SCRATCH_PREFIX}plan"
_PHASE_FILE = "livespec-groom-phase"
_DRAFT_FILE = "livespec-groom-draft"
_PLAN_FILE = "livespec-groom-plan"

_BRANCH = "master"
# A conformant filing plan: one line, no brace, opening with the marker the
# Dispatcher discriminates a plan from a draft by.
_PLAN_LINE = "livespec-groom-plan: slice-one | slice-two | regroom the original out\n"

# A rendered workflow input token. `{` alone is NOT this pattern: the gate's own
# brace check greps for a single literal brace, and that must survive rendering.
_INPUT_TOKEN = re.compile(r"\{\{[^{}]*\}\}")
_CONFORMANCE_EDGE = re.compile(r"^conformance\s*->\s*(?P<target>\w+)\b")

# (case, draft body or None for "no draft file at all", expected exit code)
_PROPOSE_CASES = (
    ("a conformant one-line draft", "one conformant line\n", 0),
    ("no draft at all", None, 1),
    ("an empty draft", "", 1),
    ("a draft spanning two lines", "first line\nsecond line\n", 1),
    ("a draft carrying a brace", "a line with a { in it\n", 1),
)


def test_the_apply_phase_without_a_filing_plan_is_refused(tmp_path: Path) -> None:
    """The filed defect, driven: the shape that once passed vacuously now fails."""
    completed = _run_gate(tmp_path=tmp_path, phase="apply", products={})

    assert completed.returncode == 1
    assert _SENTINEL in completed.stderr
    assert "the apply phase produced nothing" in completed.stderr
    assert _PLAN_FILE in completed.stderr
    assert completed.stdout == ""


def test_the_apply_phase_with_an_empty_filing_plan_is_refused(tmp_path: Path) -> None:
    """Present-but-empty is the same refusal: the criterion is NON-empty."""
    completed = _run_gate(tmp_path=tmp_path, phase="apply", products={_PLAN_FILE: ""})

    assert completed.returncode == 1
    assert _SENTINEL in completed.stderr
    assert "the apply phase produced nothing" in completed.stderr


def test_the_apply_phase_with_a_filing_plan_passes(tmp_path: Path) -> None:
    """The control: without this, a gate that refused EVERY apply would also pass above."""
    completed = _run_gate(tmp_path=tmp_path, phase="apply", products={_PLAN_FILE: _PLAN_LINE})

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert completed.stdout == ""


@pytest.mark.parametrize(
    ("case", "draft", "expected_code"),
    _PROPOSE_CASES,
    ids=[case for case, _, _ in _PROPOSE_CASES],
)
def test_the_propose_phase_checks_still_hold(
    tmp_path: Path, case: str, draft: str | None, expected_code: int
) -> None:
    """Existence, one-line and brace-free, unchanged — and shared with the apply phase.

    The three product checks are ONE code path parameterised by phase, so
    driving them here proves them for the apply phase's plan too; only the
    phase-specific arms (which product, and the plan's marker) are separate.
    """
    products = {} if draft is None else {_DRAFT_FILE: draft}

    completed = _run_gate(tmp_path=tmp_path, phase="propose", products=products)

    assert completed.returncode == expected_code, case
    assert (_SENTINEL in completed.stderr) is bool(expected_code), case


def test_a_refused_conformance_cannot_reach_the_review_node() -> None:
    """The graph half of "before any review turn": review is behind a succeeded gate."""
    edges = [
        line.strip()
        for line in _graph_text().splitlines()
        if not line.strip().startswith("//") and _CONFORMANCE_EDGE.match(line.strip())
    ]

    # A control on the reader before believing what it says about the targets:
    # a parse returning some other count would make the comparison meaningless
    # rather than false.
    assert len(edges) == 3
    targets = {_edge_target(edge=edge) for edge in edges}
    assert targets == {"review", "fix", "non_converged"}

    to_review = [edge for edge in edges if _edge_target(edge=edge) == "review"]
    assert len(to_review) == 1
    assert 'condition="outcome=succeeded"' in to_review[0]


def test_the_gate_script_carries_no_apply_phase_short_circuit() -> None:
    """The filed regression pinned as a SHAPE as well as a behaviour.

    The positive control matters more than the negative assertion here: the gate
    legitimately branches on the phase, so `= apply` must be findable. Without
    that control an anchored pattern that could never match would report a clean
    negative for a reinstated short-circuit exactly as it does for an absent one.
    """
    script = _conformance_script()

    assert re.search(r"=\s*apply", script) is not None
    assert re.search(r"=\s*apply\s*;\s*then\s+exit\s+0", script) is None


def _graph_text() -> str:
    """The graph a dispatch would run, resolved through the registry a dispatch resolves it with."""
    variant = resolve_workflow_variant(cwd=_REPO_ROOT, name=_GROOM_VARIANT_NAME)
    resolved = workflow_toml(
        args=argparse.Namespace(workflow=None, repo=_REPO_ROOT),
        variant_directory=variant.directory,
    )
    return (resolved.parent / "workflow.fabro").read_text(encoding="utf-8")


def _conformance_script() -> str:
    """The conformance node's own script, unescaped from the DOT attribute."""
    node = re.search(
        r"^\s*conformance\s*\[(?P<body>.*?)^\s*\]", _graph_text(), re.DOTALL | re.MULTILINE
    )
    assert node is not None
    attribute = re.search(r'script="(?P<script>(?:[^"\\]|\\.)*)"', node.group("body"))
    assert attribute is not None
    return re.sub(r"\\(?P<escaped>.)", r"\g<escaped>", attribute.group("script"))


def _rendered_script(*, scratch: Path) -> str:
    """The script as a script node receives it, with its scratch root moved into `tmp_path`."""
    script = _conformance_script()

    # The shipped text names the real paths the prompt writes and the review
    # node reads; assert that BEFORE re-rooting, so the substitution below
    # cannot mask a drift between the three.
    assert _PHASE_PATH in script
    assert _DRAFT_PATH in script
    assert _PLAN_PATH in script

    rendered, rendered_count = _INPUT_TOKEN.subn(_BRANCH, script)
    assert rendered_count > 0
    assert _INPUT_TOKEN.search(rendered) is None

    assert rendered.count(_SCRATCH_PREFIX) > 0
    return rendered.replace(_SCRATCH_PREFIX, f"{scratch}/livespec-groom-")


def _run_gate(
    *, tmp_path: Path, phase: str, products: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run the gate over a groom-shaped sandbox: a clean checkout and the named products."""
    work, scratch = _sandbox(tmp_path=tmp_path)
    (scratch / _PHASE_FILE).write_text(f"{phase}\n", encoding="utf-8")
    for name, body in products.items():
        (scratch / name).write_text(body, encoding="utf-8")
    return subprocess.run(
        ["sh", "-c", _rendered_script(scratch=scratch)],
        cwd=str(work),
        check=False,
        text=True,
        capture_output=True,
    )


def _sandbox(*, tmp_path: Path) -> tuple[Path, Path]:
    """A groom sandbox: a checkout identical to its dispatch base, and an empty scratch root."""
    work = tmp_path / "work"
    work.mkdir(parents=True)
    _git(work, "init", "--quiet")
    _git(work, "config", "user.email", "fixture@example.invalid")
    _git(work, "config", "user.name", "Fixture")
    _git(work, "config", "commit.gpgsign", "false")
    (work / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "--quiet", "-m", "seed")
    # The gate diffs the checkout against `origin/<default branch>`. A groom run
    # files into the ledger and changes no tracked file, so the conforming
    # fixture is one whose remote-tracking ref IS its HEAD; every case here is
    # about the PRODUCT check, so none of them may trip the tree check first.
    _git(work, "update-ref", f"refs/remotes/origin/{_BRANCH}", "HEAD")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    return work, scratch


def _edge_target(*, edge: str) -> str:
    match = _CONFORMANCE_EDGE.match(edge)
    assert match is not None
    return match.group("target")


def _git(repo: Path, *argv: str) -> None:
    subprocess.run(["git", *argv], cwd=str(repo), check=True, text=True, capture_output=True)
