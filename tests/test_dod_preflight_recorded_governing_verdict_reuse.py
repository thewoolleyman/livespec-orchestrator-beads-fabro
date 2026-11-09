"""The repository preflight reads a current governing-heading verdict before it spends a model.

The pre-dispatch gate consults `reusable_governing_heading_verdict` before it asks
the host reader for a governing-heading judgement (`_dispatcher_dod_judgement_gate.py`).
The preflight called the host reader on every run, so a launch re-took a judgement
the item already carried a current record for, and the retaking could flip the
verdict on identical bytes (`bd-ib-ot4av7`).

WHY THIS IS A CONTENT TEST, for the reason `test_dod_preflight_spec_stated_judgement.py`
gives: the script resolves its build from the operator host's plugin registry and
reads the live tenant. What a sandbox can establish is that the committed script
DELEGATES to the component's own reuse function, which owns the three behaviours the
Definition of Done names: a record whose subject digest and clauses are current is
reused, a changed subject (a candidate edit) is not, and a standing `release-spec-tier`
attestation is read first.
"""

from __future__ import annotations

from pathlib import Path

_SCRIPT = Path("dev-tooling/dod-preflight.sh")
_REUSE = "reusable_governing_heading_verdict(item=item, repo=repo, comments=comments)"
_READER = "host_governing_heading_reader(runner=ShellCommandRunner())(item=item, repo=repo)"


def _script() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def test_the_preflight_reads_the_components_reuse_function_with_the_gates_arguments() -> None:
    assert _REUSE in _script()


def test_the_host_reader_runs_only_when_no_recorded_verdict_is_reusable() -> None:
    text = _script()

    assert _REUSE in text
    reuse_at = text.index(_REUSE)
    guard = "if governing is None:"

    assert text.index(guard, reuse_at) > reuse_at
    assert text.index(_READER) > text.index(guard, reuse_at)
    assert text.count(_READER) == 1


def test_the_reuse_reads_the_candidate_edit_not_the_ledger_description() -> None:
    # The digest the reuse compares is computed from `item.description`, so the
    # read must come after the candidate description replaces it.
    text = _script()

    assert _REUSE in text
    assert text.index("item = replace(item, description=") < text.index(_REUSE)


def test_the_reuse_import_holds_on_a_build_that_predates_the_component() -> None:
    # The script runs against the REGISTERED build; one without the module must
    # fall back to the host taking rather than die at import.
    text = _script()

    assert "_dispatcher_dod_governing_reuse import" in text
    import_at = text.index("_dispatcher_dod_governing_reuse import")

    assert text.rindex("try:", 0, import_at) > text.index("PROMPT_PY")
    assert text.index("except ImportError", import_at) < text.index(_REUSE)
