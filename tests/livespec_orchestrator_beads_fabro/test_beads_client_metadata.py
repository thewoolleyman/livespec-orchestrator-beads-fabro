"""What one metadata write carries, and how the server's merge applies it."""

from __future__ import annotations

from typing import Any

import pytest
from livespec_orchestrator_beads_fabro import _store_claim_tokens, _store_dispatch_claim
from livespec_orchestrator_beads_fabro._beads_client_metadata import (
    CLAIM_TOKEN_METADATA_KEY,
    merged_metadata,
    metadata_payload,
)


def test_the_token_key_keeps_its_name_and_every_module_that_exported_it_still_does() -> None:
    assert CLAIM_TOKEN_METADATA_KEY == "dispatch_claim_token"
    assert _store_claim_tokens.CLAIM_TOKEN_METADATA_KEY is CLAIM_TOKEN_METADATA_KEY
    assert _store_dispatch_claim.CLAIM_TOKEN_METADATA_KEY is CLAIM_TOKEN_METADATA_KEY


def test_a_payload_outside_the_protocol_is_a_copy_without_the_token_key() -> None:
    metadata = {"rank": "a8", CLAIM_TOKEN_METADATA_KEY: "fake-wisp-1", "audit": {"commits": []}}

    payload = metadata_payload(metadata=metadata, names_claim_token=False)

    assert payload == {"rank": "a8", "audit": {"commits": []}}
    assert metadata[CLAIM_TOKEN_METADATA_KEY] == "fake-wisp-1"


def test_a_payload_that_held_only_the_token_key_sends_nothing_and_an_empty_one_stays_empty() -> (
    None
):
    only_the_token = metadata_payload(
        metadata={CLAIM_TOKEN_METADATA_KEY: "fake-wisp-3"}, names_claim_token=False
    )
    empty = metadata_payload(metadata={}, names_claim_token=False)

    assert only_the_token is None
    assert empty == {}


def test_a_protocol_payload_is_a_copy_that_keeps_the_token_key() -> None:
    metadata = {"rank": "a8", CLAIM_TOKEN_METADATA_KEY: "fake-wisp-2"}

    payload = metadata_payload(metadata=metadata, names_claim_token=True)

    assert payload == metadata
    assert payload is not metadata


def test_an_update_that_carries_no_metadata_sends_none_and_stores_none() -> None:
    assert metadata_payload(metadata=None, names_claim_token=False) is None
    assert metadata_payload(metadata=None, names_claim_token=True) is None
    assert merged_metadata(stored={"rank": "a0"}, payload=None) is None


def test_the_merge_replaces_each_top_level_key_sent_and_keeps_each_one_omitted() -> None:
    stored = {"rank": "a0", "audit": {"commits": ["c1"], "merge_sha": "m1"}, "kept": True}

    merged = merged_metadata(stored=stored, payload={"rank": "a8", "audit": {"commits": ["c2"]}})

    assert merged == {"rank": "a8", "audit": {"commits": ["c2"]}, "kept": True}
    assert stored == {"rank": "a0", "audit": {"commits": ["c1"], "merge_sha": "m1"}, "kept": True}


@pytest.mark.parametrize("stored", [None, "not-an-object", ["rank"]])
def test_a_record_that_holds_no_metadata_object_takes_the_payload_whole(stored: Any) -> None:
    payload = {"rank": "a8"}

    merged = merged_metadata(stored=stored, payload=payload)

    assert merged == {"rank": "a8"}
    assert merged is not payload
