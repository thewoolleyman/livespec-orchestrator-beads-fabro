"""Mirror coverage for the effects package public exports."""

from livespec_orchestrator_beads_fabro import effects

__all__: list[str] = []


def test_effects_exports_expected_error_boundaries() -> None:
    assert effects.__all__ == [
        "AttemptFailure",
        "FloatParseFailure",
        "IsoDatetimeParseFailure",
        "JsonParseFailure",
        "attempt",
        "parse_float",
        "parse_iso_datetime",
        "parse_json",
    ]
