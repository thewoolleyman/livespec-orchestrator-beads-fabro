"""The master-CI preflight guidance file, graded as the agent-facing surface it is.

Each test here grades ONE assertion of `bd-ib-2jfzgr`'s Definition of Done against
`.ai/master-ci-green-preflight.md`. The file told every agent routed to it that a
pending latest run is an UNPROVABLE refusal, which stopped being true when the
bounded wait landed; sessions acting on the stale text added their own ci-green
pre-checks to launch loops and skipped launch slots the dispatcher would have
admitted. So the assertions here are about what the file SAYS, and about one thing
that is not its contents: AGENTS.md must still ROUTE an agent to it, since the
`.ai/` resolve check verifies that references RESOLVE and never that one was made.

Every content assertion runs against the WHITESPACE-FLATTENED text. A phrase this
file wraps across a line would otherwise be absent as a literal while present as
prose, which would make a negative assertion pass for the wrong reason — the
stale-sentence checks below are exactly where that silent pass would cost the most.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RELPATH = ".ai/master-ci-green-preflight.md"
_AGENT_INSTRUCTIONS = (_REPO_ROOT / "AGENTS.md").read_text()
_GUIDANCE_PATH = _REPO_ROOT / _RELPATH


def _guidance() -> str:
    """Read the guidance file flattened to one line, failing as a missing-file assertion."""
    assert _GUIDANCE_PATH.is_file(), f"{_RELPATH} does not exist"
    return " ".join(_GUIDANCE_PATH.read_text().split())


def test_guidance_states_the_bounded_wait_a_pending_run_earns() -> None:
    guidance = _guidance()

    # Routed from AGENTS.md: the resolve check proves a reference resolves, never that
    # one was made, so the reachability of this file is asserted here or nowhere.
    assert _RELPATH in _AGENT_INSTRUCTIONS

    # The bound and the cadence, as the ratified clause states them.
    assert "waits up to 1800 seconds" in guidance
    assert "polling every 60 seconds" in guidance

    # The five pending statuses that earn the wait. Asserted one by one rather than as
    # one sentence fragment, so a file keeping only some of them cannot pass.
    for status in ("`queued`", "`in_progress`", "`waiting`", "`pending`", "`requested`"):
        assert status in guidance, status

    # What a refusal on the run's own verdict now requires.
    assert "refuses only on a concluded run that is not green" in guidance

    # And the stale claim is GONE. A file that adds the wait while leaving the old
    # sentences standing contradicts itself, and a reader acting on either half still
    # skips the launch slot this item exists to recover.
    assert "refused as unprovable, not admitted" not in guidance
    assert "an UNPROVABLE refusal" not in guidance


def test_guidance_names_the_module_holding_the_bounded_wait() -> None:
    guidance = _guidance()

    # The module an agent reads to check the bound for itself, rather than trusting a
    # number in prose that has already gone stale once.
    assert "`_dispatcher_ci_preflight_wait.py`" in guidance
    assert "holds that bounded wait" in guidance
