"""A factory entry's optional GitHub App secret-name declaration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

__all__: list[str] = [
    "FACTORY_GITHUB_APP_KEY",
    "NO_FACTORY_GITHUB_APP",
    "FactoryGithubApp",
    "factory_github_app_from_entry",
    "factory_github_app_refusal",
    "github_app_secret_names",
    "github_app_table",
]

FACTORY_GITHUB_APP_KEY = "github_app"
_APP_ID_FIELD = "app_id_secret"
_PRIVATE_KEY_FIELD = "private_key_secret"
_REQUIRED_KEYS = frozenset({_APP_ID_FIELD, _PRIVATE_KEY_FIELD})


@dataclass(frozen=True, kw_only=True)
class FactoryGithubApp:
    """A factory's GitHub App declaration as read, before it is graded."""

    declared: bool = False
    is_object: bool = False
    app_id_secret: object = None
    private_key_secret: object = None
    extra_keys: tuple[str, ...] = ()


NO_FACTORY_GITHUB_APP = FactoryGithubApp()


def factory_github_app_from_entry(*, entry: dict[str, Any]) -> FactoryGithubApp:
    """Read `github_app` without collapsing a malformed declaration to absence."""
    if FACTORY_GITHUB_APP_KEY not in entry:
        return NO_FACTORY_GITHUB_APP
    raw: object = entry[FACTORY_GITHUB_APP_KEY]
    if not isinstance(raw, dict):
        return FactoryGithubApp(declared=True)
    value = cast("dict[str, object]", raw)
    keys: tuple[str, ...] = tuple(key for key in value if key not in _REQUIRED_KEYS)
    return FactoryGithubApp(
        declared=True,
        is_object=True,
        app_id_secret=value.get(_APP_ID_FIELD),
        private_key_secret=value.get(_PRIVATE_KEY_FIELD),
        extra_keys=keys,
    )


def github_app_secret_names(*, github_app: FactoryGithubApp) -> tuple[str, str] | None:
    """Return the usable secret names, or None for the absent or invalid shapes."""
    if (
        not github_app.declared
        or not github_app.is_object
        or github_app.extra_keys
        or not isinstance(github_app.app_id_secret, str)
        or github_app.app_id_secret == ""
        or not isinstance(github_app.private_key_secret, str)
        or github_app.private_key_secret == ""
    ):
        return None
    return github_app.app_id_secret, github_app.private_key_secret


def _toml_string(*, value: str) -> str:
    """One TOML basic string; DEL is escaped because TOML forbids it raw."""
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")


def github_app_table(*, github_app: FactoryGithubApp) -> str:
    """Render the optional run-integration table from already-validated names."""
    names = github_app_secret_names(github_app=github_app)
    if names is None:
        return ""
    return (
        "\n[run.integrations.github.app]\n"
        f"app_id_secret = {_toml_string(value=names[0])}\n"
        f"private_key_secret = {_toml_string(value=names[1])}\n"
    )


def factory_github_app_refusal(*, factory: str, github_app: FactoryGithubApp) -> str | None:
    """Refuse malformed GitHub App declarations before a dispatch claims work."""
    if not github_app.declared:
        return None
    path = f"dispatcher.factories.{factory}.{FACTORY_GITHUB_APP_KEY}"
    if not github_app.is_object:
        return f"ERROR: {path} must be an object with app_id_secret and private_key_secret names\n"
    if github_app.extra_keys:
        return f"ERROR: {path} contains unsupported key(s): {', '.join(github_app.extra_keys)}\n"
    if not isinstance(github_app.app_id_secret, str) or github_app.app_id_secret == "":
        return f"ERROR: {path}.app_id_secret must be a non-empty string secret name\n"
    if not isinstance(github_app.private_key_secret, str) or github_app.private_key_secret == "":
        return f"ERROR: {path}.private_key_secret must be a non-empty string secret name\n"
    return None
