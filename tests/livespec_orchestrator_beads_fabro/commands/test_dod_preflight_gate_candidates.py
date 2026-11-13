"""The preflight's dod_gate chain falls back to the legacy string form only when it is one."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_MODULE = "livespec_orchestrator_beads_fabro.commands._dod_preflight_judgement"


def _repo(*, tmp_path: Path, block: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".livespec.jsonc").write_text(
        f'{{"livespec-orchestrator-beads-fabro":{{"dispatcher":{block}}}}}', encoding="utf-8"
    )
    return repo


@pytest.mark.parametrize(
    "block",
    ["{}", '{"acp_nodes":null}', '{"acp_nodes":{}}', '{"acp_nodes":{"dod_gate":{"agent":"x"}}}'],
)
def test_an_unresolved_chain_with_no_legacy_string_resolves_no_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, block: str
) -> None:
    judgement = importlib.import_module(_MODULE)
    monkeypatch.setattr(judgement, "dod_gate_candidates", lambda **_: None)

    assert (
        judgement.preflight_dod_gate_candidates(cwd=_repo(tmp_path=tmp_path, block=block)) is None
    )


def test_a_resolved_chain_is_returned_as_the_gate_resolved_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    judgement = importlib.import_module(_MODULE)
    monkeypatch.setattr(judgement, "dod_gate_candidates", lambda **_: ())

    assert judgement.preflight_dod_gate_candidates(cwd=tmp_path) == ()
