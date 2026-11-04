"""Unit coverage for factory GitHub App declaration parsing and refusal."""

from __future__ import annotations

import pytest
import tomli
from livespec_orchestrator_beads_fabro.commands._factory_github_app import (
    factory_github_app_from_entry,
    factory_github_app_refusal,
    github_app_secret_names,
    github_app_table,
)


@pytest.mark.parametrize(
    "value",
    [None, "name", [], {"app_id_secret": "id"}, {"private_key_secret": "key"}, {"extra": "x"}],
)
def test_malformed_factory_github_app_is_refused_without_a_table(value: object) -> None:
    """Every malformed declaration names its source path before claim."""
    app = factory_github_app_from_entry(entry={"github_app": value})

    refusal = factory_github_app_refusal(factory="petri", github_app=app)

    assert refusal is not None
    assert "dispatcher.factories.petri.github_app" in refusal
    assert github_app_secret_names(github_app=app) is None
    assert github_app_table(github_app=app) == ""


def test_absent_factory_github_app_is_not_refused() -> None:
    """An undeclared app keeps the server's global integration."""
    app = factory_github_app_from_entry(entry={})

    assert factory_github_app_refusal(factory="petri", github_app=app) is None


def test_valid_factory_github_app_is_not_refused() -> None:
    """The declaration grade admits exactly the usable secret-name shape."""
    app = factory_github_app_from_entry(
        entry={"github_app": {"app_id_secret": "APP_ID", "private_key_secret": "PRIVATE_KEY"}}
    )

    assert factory_github_app_refusal(factory="petri", github_app=app) is None


@pytest.mark.parametrize(
    "name",
    [
        'QUOTE"NAME',
        "LINE\nBREAK",
        'EVIL"\n[run.injected]\nx = "1',
        "BACK\\SLASH",
        "UNICODE\u00e9\x7f",
    ],
)
def test_rendered_table_round_trips_the_declared_names_as_toml_strings(name: str) -> None:
    """Secret names are serialized as TOML strings, so the overlay carries exactly them."""
    app = factory_github_app_from_entry(
        entry={"github_app": {"app_id_secret": name, "private_key_secret": name + "_KEY"}}
    )

    parsed = tomli.loads(github_app_table(github_app=app))

    assert parsed == {
        "run": {
            "integrations": {
                "github": {"app": {"app_id_secret": name, "private_key_secret": name + "_KEY"}}
            }
        }
    }
