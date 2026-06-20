"""Seed sanity test — keeps `just check` (pytest) green on the seeded tree.

Exists so the skeleton's check suite is non-empty and green BEFORE the Fabro
agent implements `greet`. The agent adds `tests/test_greet.py` asserting the
greeting; both run under the same `just check`.
"""


def test_skeleton_is_present() -> None:
    assert 1 + 1 == 2
