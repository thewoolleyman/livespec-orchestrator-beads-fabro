"""The reflector's host judgement follows the resolved ACP candidate order."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_candidate_schema import AcpCandidate
from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import AcpAdapter


def test_first_parseable_candidate_reply_decides_without_starting_a_later_candidate() -> None:
    """A Codex verdict is final; no later configured candidate is launched."""
    module_path = (
        Path(__file__).parents[3]
        / ".claude-plugin"
        / "scripts"
        / "livespec_orchestrator_beads_fabro"
        / "commands"
        / "_reflector_acp_chain.py"
    )
    assert module_path.is_file()
    chain = import_module("livespec_orchestrator_beads_fabro.commands._reflector_acp_chain")
    primary = AcpCandidate(
        adapter=AcpAdapter(command="codex-acp"),
        agent_id="codex-acp",
    )
    fallback = AcpCandidate(
        adapter=AcpAdapter(command="claude-acp"),
        agent_id="claude-acp",
    )
    launched: list[str] = []

    def invoke(*, candidate: AcpCandidate) -> str | None:
        launched.append(candidate.agent_id or "")
        return '{"findings": []}'

    reply = chain.first_verdict(
        candidates=(primary, fallback),
        invoke=invoke,
        is_verdict=lambda text: text.startswith("{"),
    )

    assert reply == '{"findings": []}'
    assert launched == ["codex-acp"]


def test_unparseable_or_missing_replies_fall_through_in_candidate_order() -> None:
    """Only a parseable reply settles the judgement chain."""
    module_path = (
        Path(__file__).parents[3]
        / ".claude-plugin"
        / "scripts"
        / "livespec_orchestrator_beads_fabro"
        / "commands"
        / "_reflector_acp_chain.py"
    )
    assert module_path.is_file()
    chain = import_module("livespec_orchestrator_beads_fabro.commands._reflector_acp_chain")
    primary = AcpCandidate(adapter=AcpAdapter(command="codex-acp"), agent_id="codex-acp")
    fallback = AcpCandidate(adapter=AcpAdapter(command="claude-acp"), agent_id="claude-acp")
    replies = iter((None, "not structured"))

    def invoke(*, candidate: AcpCandidate) -> str | None:
        _ = candidate
        return next(replies)

    reply = chain.first_verdict(
        candidates=(primary, fallback),
        invoke=invoke,
        is_verdict=lambda text: text.startswith("{"),
    )

    assert reply is None
