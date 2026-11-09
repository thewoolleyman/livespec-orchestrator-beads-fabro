"""The preflight script takes its governing-heading lines from the package's reading seam.

The behaviours the Definition of Done names (a current recorded verdict starts no
judge candidate, a changed subject starts one, a standing `release-spec-tier`
attestation yields the gate's verdict) are proved in
`tests/livespec_orchestrator_beads_fabro/commands/test_dod_preflight_governing_reading.py`
against a recording runner. What a sandbox can establish about the SCRIPT, whose
end-to-end run needs the operator host's plugin registry and live tenant, is that
the committed script delegates to that seam with the comment texts it already reads
and a shell command runner, and calls the host reader itself only on a registered
build that predates the seam (`bd-ib-ot4av7`).
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path("dev-tooling/dod-preflight.sh")
_SEAM = "preflight_governing_heading_reading"
_CALL = f"reading = {_SEAM}(\n    item=item, repo=repo, comments=comments, runner=ShellCommandRunner()\n)"
_MODULE = "_dod_preflight_governing_reading import"


def _script() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def test_the_preflight_takes_its_lines_from_the_reading_with_its_comments_and_a_shell_runner() -> (
    None
):
    text = _script()

    assert _CALL in text
    assert "reading.report" in text
    assert "reading.findings" in text
    assert "reading.holds" in text


def test_the_reading_sees_the_candidate_edit_and_the_comments_the_script_already_reads() -> None:
    # The reuse digest is computed from `item.description`, so the reading must
    # come after the candidate description replaces it and after the comments are read.
    text = _script()

    call_at = text.index(_CALL)
    assert text.index("item = replace(item, description=") < call_at
    assert text.index("comments = tuple(") < call_at


def test_the_host_reader_is_called_only_by_the_old_build_fallback() -> None:
    text = _script()

    assert text.count("host_governing_heading_reader(") == 1
    assert text.index("except ImportError:") < text.index("host_governing_heading_reader(")
    assert text.index("host_governing_heading_reader(") < text.index(_CALL)


def test_the_seam_import_holds_on_a_build_that_predates_the_module() -> None:
    # The script runs against the REGISTERED build; one without the module must
    # fall back to the host taking rather than die at import.
    text = _script()
    import_at = text.index(_MODULE)

    assert text.rindex("try:", 0, import_at) > text.index("PROMPT_PY")
    assert text.index("except ImportError", import_at) < text.index(_CALL)
