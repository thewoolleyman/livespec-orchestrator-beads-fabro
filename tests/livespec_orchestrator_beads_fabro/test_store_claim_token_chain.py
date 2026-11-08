"""Where a claim-token chain ends, read for many items at once.

`read_chain_ends` is what lets `needs-attention` tell an item no claim writer
can ever win from one whose transition the writers will take over themselves.
These cases pin the three answers it gives (open, dead end, unobservable), that
only the protocol's own discard or a cycle is a dead end, and that the walk
costs one `bd show` per hop depth rather than one per token.
"""

from __future__ import annotations

import json
from itertools import pairwise

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient
from livespec_orchestrator_beads_fabro._store_claim_token_chain import (
    CHAIN_DEAD_END,
    CHAIN_OPEN,
    CHAIN_UNOBSERVABLE,
    ChainEnd,
    discard_claim_token,
    is_discard_reason,
    read_chain_ends,
    successor_named_by,
    transition_reason,
)
from livespec_orchestrator_beads_fabro._store_dispatch_claim import create_claim_token


def _closed_naming(*, client: FakeBeadsClient, token: str, successor: str) -> None:
    client.close_issue(
        issue_id=token,
        reason=transition_reason(writer="w", intent="i", successor=successor),
    )


def test_each_chain_ends_open_dead_or_unobservable() -> None:
    client = FakeBeadsClient()
    open_token = create_claim_token(client=client)
    hop, hop_successor = create_claim_token(client=client), create_claim_token(client=client)
    _closed_naming(client=client, token=hop, successor=hop_successor)
    stranded, discarded = create_claim_token(client=client), create_claim_token(client=client)
    _closed_naming(client=client, token=stranded, successor=discarded)
    discard_claim_token(client=client, token_id=discarded, writer="takeover")
    gone, never = "fake-wisp-gone", "fake-wisp-never"
    to_missing = create_claim_token(client=client)
    _closed_naming(client=client, token=to_missing, successor=gone)
    by_hand = create_claim_token(client=client)
    client.close_issue(issue_id=by_hand, reason="closed by hand")

    ends = read_chain_ends(
        client=client,
        token_ids=[open_token, hop, stranded, to_missing, by_hand, never],
    )

    assert ends == {
        open_token: ChainEnd(token_id=open_token, state=CHAIN_OPEN),
        hop: ChainEnd(token_id=hop_successor, state=CHAIN_OPEN),
        stranded: ChainEnd(token_id=discarded, state=CHAIN_DEAD_END),
        to_missing: ChainEnd(token_id=gone, state=CHAIN_UNOBSERVABLE),
        by_hand: ChainEnd(token_id=by_hand, state=CHAIN_UNOBSERVABLE),
        never: ChainEnd(token_id=never, state=CHAIN_UNOBSERVABLE),
    }


def test_a_chain_that_leads_back_into_itself_is_a_dead_end() -> None:
    client = FakeBeadsClient()
    first, second = create_claim_token(client=client), create_claim_token(client=client)
    _closed_naming(client=client, token=first, successor=second)
    _closed_naming(client=client, token=second, successor=first)

    assert read_chain_ends(client=client, token_ids=[first]) == {
        first: ChainEnd(token_id=second, state=CHAIN_DEAD_END)
    }


def test_the_walk_is_one_show_per_hop_depth_and_none_for_no_tokens() -> None:
    client = FakeBeadsClient()
    chain = [create_claim_token(client=client) for _ in range(4)]
    for token, successor in pairwise(chain):
        _closed_naming(client=client, token=token, successor=successor)
    short = create_claim_token(client=client)
    shows: list[list[str]] = []
    real = client.show_issues

    def _counting(*, issue_ids: list[str]) -> list[dict[str, object]]:
        shows.append(list(issue_ids))
        # A record the show returns without an id is skipped, never indexed.
        return [*real(issue_ids=issue_ids), {"status": "open"}]

    client.show_issues = _counting  # type: ignore[method-assign]

    ends = read_chain_ends(client=client, token_ids=[chain[0], chain[1], short, chain[0]])

    assert ends[chain[0]] == ends[chain[1]] == ChainEnd(token_id=chain[3], state=CHAIN_OPEN)
    assert ends[short] == ChainEnd(token_id=short, state=CHAIN_OPEN)
    assert shows == [sorted([chain[0], chain[1], short]), [chain[2]], [chain[3]]]
    assert read_chain_ends(client=client, token_ids=[]) == {}


def test_reason_readers_agree_on_what_a_protocol_reason_is() -> None:
    transition = transition_reason(writer="w", intent="i", successor="fake-wisp-9")
    discard = json.dumps({"kind": "claim-token-discard", "writer": "w"})

    assert successor_named_by(reason=transition) == "fake-wisp-9"
    assert successor_named_by(reason=discard) is None
    assert is_discard_reason(reason=discard) is True
    assert is_discard_reason(reason=transition) is False
    assert successor_named_by(reason='{"kind":"claim-token-transition","successor":" "}') is None
    for other in (None, "not-json", "[]", '{"kind":"other"}'):
        assert successor_named_by(reason=other) is None
        assert is_discard_reason(reason=other) is False
