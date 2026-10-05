"""The `.ai/` host-captured proof guidance states what work-item bd-ib-sy6gpv requires.

Documentation-content assertions, in the style of `test_host_fabro_runbook.py`:
the guidance file IS the deliverable here, so its load-bearing sentences are
gated rather than left to drift out from under the AGENTS.md reference that
routes an agent to them.

The guidance file is read INSIDE each test rather than at module import, so an
absent file fails on a genuine assertion instead of dying at collection — a
collection error would prove only that the path is unreadable, never that the
guidance is unwritten.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GUIDANCE_REL = ".ai/host-captured-proof-and-replay.md"
_GUIDANCE_PATH = _REPO_ROOT / _GUIDANCE_REL
_AGENT_INSTRUCTIONS = (_REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

_PROCEDURE_HEADING = "## The procedure, in order"

# One token per ordered step of the host-captured procedure. Each is a phrase
# the step cannot be stated without, and the search is SCOPED to the procedure
# section, so a step named only in passing elsewhere in the file cannot satisfy
# it and a step present but out of order still fails the index comparison.
_ORDERED_STEPS = (
    "`Host-captured` sub-heading",
    "`Reason:`",
    "rests in acceptance",
    "against the released build",
    "`post-host-record`",
    "separately started agent session",
)


def _guidance() -> str:
    assert _GUIDANCE_PATH.is_file(), f"{_GUIDANCE_PATH} is not a file"
    return _GUIDANCE_PATH.read_text(encoding="utf-8")


def _procedure_section() -> str:
    text = _guidance()
    assert _PROCEDURE_HEADING in text, f"{_GUIDANCE_REL} carries no {_PROCEDURE_HEADING!r}"
    return text.split(_PROCEDURE_HEADING, 1)[1].split("\n## ", 1)[0]


def test_agent_instructions_route_to_the_host_captured_proof_guidance() -> None:
    assert _GUIDANCE_REL in _AGENT_INSTRUCTIONS


def test_guidance_states_the_host_captured_procedure_in_order() -> None:
    section = _procedure_section()
    positions = [section.find(step) for step in _ORDERED_STEPS]
    missing = [step for step, at in zip(_ORDERED_STEPS, positions, strict=False) if at < 0]
    assert not missing, f"{_GUIDANCE_REL} procedure section omits {missing}"
    assert positions == sorted(positions), (
        f"{_GUIDANCE_REL} states the procedure out of order: "
        f"{list(zip(_ORDERED_STEPS, positions, strict=False))}"
    )


def test_guidance_states_an_ancestor_seed_cannot_demonstrate_a_refusal() -> None:
    text = _guidance()

    # The seed's defect and its consequence, separately: a branch at an
    # ancestor of master is silently fast-forwarded, so the observation it
    # was staged to produce — the refusal, and the reclaim the refusal
    # motivates — is unreachable from it.
    assert "ancestor of master" in text
    assert "fast-forwarded by the next run" in text
    assert "non-fast-forward" in text
    assert "reclaim" in text
    # And the remedy, which is the half an operator acts on.
    assert "a commit master does not contain" in text


def test_guidance_states_a_herdr_pane_finishes_done_rather_than_idle() -> None:
    text = _guidance()

    # The fact: the terminal status of a finished agent pane is `done`, and
    # `idle` is a DIFFERENT status, not a synonym reached on the way out.
    assert "herdr" in text
    assert "`done` rather than `idle`" in text
    # The consequence for a wait, which is where the three hours went.
    assert "accept either word" in text
    # A token the remedy cannot be stated without: the invocation that waits
    # on both. `--until idle` alone is exactly the defect, so asserting the
    # two-flag form is what discriminates a stated remedy from a restated
    # problem.
    assert "--until idle --until done" in text
