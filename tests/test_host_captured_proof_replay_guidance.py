"""The host-captured proof guidance file, graded as the agent-facing surface it is.

Each test here grades ONE assertion of `bd-ib-sy6gpv`'s Definition of Done against
`.ai/host-captured-proof-replay.md`. The file is progressive-disclosure guidance, so
two things have to hold and only one of them is about its contents: it must SAY the
thing, and AGENTS.md must ROUTE an agent to it. A guidance file nothing references is
the orphaned-guidance failure the `.ai/` convention's own resolve check structurally
cannot catch — it verifies that references RESOLVE, so a repo making no reference to a
file passes with that file unreachable. Hence the reference assertion in the first test
rather than a note saying someone should check.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RELPATH = ".ai/host-captured-proof-replay.md"
_AGENT_INSTRUCTIONS = (_REPO_ROOT / "AGENTS.md").read_text()
_GUIDANCE_PATH = _REPO_ROOT / _RELPATH


def _guidance() -> str:
    """Read the guidance file, failing as a missing-file assertion rather than OSError."""
    assert _GUIDANCE_PATH.is_file(), f"{_RELPATH} does not exist"
    return _GUIDANCE_PATH.read_text()


def test_guidance_states_the_host_captured_procedure_in_order() -> None:
    guidance = _guidance()

    # Routed from AGENTS.md: the resolve check proves a reference resolves, never that
    # one was made, so the reachability of this file is asserted here or nowhere.
    assert _RELPATH in _AGENT_INSTRUCTIONS

    # The five steps, as the ordered procedure the Definition of Done names. Each
    # marker is the step's own numbered heading, so the index comparison below grades
    # ORDER and not merely presence — a file carrying all five in the wrong sequence
    # would pass a presence-only check while telling an operator to capture before the
    # item has merged.
    steps = (
        "### 1. Declare the assertion under `Host-captured` with a `Reason:` line",
        "### 2. Let the merged item rest in `acceptance`",
        "### 3. Capture on the host, against the released build",
        "### 4. Publish the capture with `post-host-record`",
        "### 5. A SEPARATELY STARTED agent session replays and publishes its own verdict",
    )
    positions = [guidance.find(step) for step in steps]
    assert -1 not in positions, dict(zip(steps, positions, strict=True))
    assert positions == sorted(positions), dict(zip(steps, positions, strict=True))

    # The two halves of step 1 the approve valve actually grades.
    assert "Host-captured" in guidance
    assert "Reason:" in guidance
    # Step 4's primitive, named as it is invoked.
    assert "post-host-record" in guidance
    assert "--verdict host_recorded" in guidance
    # Step 5's two replay verdicts, and the independence the primitive computes.
    assert "--verdict host_verified" in guidance
    assert "--verdict host_not_reproduced" in guidance
