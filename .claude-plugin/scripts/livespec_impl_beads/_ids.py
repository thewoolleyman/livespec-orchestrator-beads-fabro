"""Stable-format ID generation for work-items and memos.

Per SPECIFICATION/contracts.md §"Work-items JSONL record schema",
work-item IDs follow the upstream `bd` convention `li-<6-char-base32-suffix>`.
Memo IDs use the parallel `mm-<6-char-base32-suffix>` shape.

The suffix is six lowercase base32 characters (a-z, 2-7). Randomness
comes from `secrets.token_bytes` so collision probability is negligible
under the JSONL store's append-only discipline; if two skills append
records with identical IDs in the same git commit's pre-merge state, git
merge will surface the conflict and the user resolves it like any other
race.
"""

import base64
import secrets

_SUFFIX_BYTES = 4  # 4 bytes → 32 bits → base32 yields ~7 chars; trimmed to 6.
_SUFFIX_LENGTH = 6


def new_work_item_id() -> str:
    """Return a fresh `li-XXXXXX` identifier."""
    return f"li-{_random_suffix()}"


def new_memo_id() -> str:
    """Return a fresh `mm-XXXXXX` identifier."""
    return f"mm-{_random_suffix()}"


def _random_suffix() -> str:
    raw = secrets.token_bytes(_SUFFIX_BYTES)
    encoded = base64.b32encode(raw).decode("ascii").lower()
    return encoded[:_SUFFIX_LENGTH]
