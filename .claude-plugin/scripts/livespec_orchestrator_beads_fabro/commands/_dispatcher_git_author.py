"""Resolve and project the operator Git author for one factory dispatch."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._jsonc import JsoncFailure, parse
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "GitAuthor",
    "GitAuthorPolicy",
    "apply_workflow_git_author",
    "git_author_env_lines",
    "read_dispatch_git_author",
    "resolve_workflow_git_author",
    "workflow_git_author_error",
]

_CONFIG_NAME = ".livespec.jsonc"
_POLICY_KEY = "git_author"
_POLICY_KEYS = frozenset({"operator_name", "operator_email", "mechanical_authors"})
_MECHANICAL_KEYS = frozenset({"name", "email"})
_AUTHOR_SECTION_RE = re.compile(r"(?ms)^\[run\.git\.author\][ \t]*\r?$(?P<body>.*?)(?=^\[|\Z)")
_JSON_STRING = r'"(?:\\(?:["\\/bfnrt]|u[0-9A-Fa-f]{4})|[^"\\\x00-\x1f])*"'


@dataclass(frozen=True, kw_only=True)
class GitAuthor:
    """One exact Git author name/email pair."""

    name: str
    email: str


@dataclass(frozen=True, kw_only=True)
class GitAuthorPolicy:
    """The operator author plus explicitly classified mechanical authors."""

    operator: GitAuthor
    mechanical_authors: tuple[GitAuthor, ...]


def read_dispatch_git_author(*, repo: Path) -> GitAuthorPolicy | str:
    """Read the target repository's author policy, or return a refusal."""
    config_path = repo / _CONFIG_NAME
    read = attempt(
        action=lambda: config_path.read_text(encoding="utf-8"),
        exceptions=(OSError,),
    )
    if isinstance(read, AttemptFailure):
        return _refusal(
            detail=f"cannot read {config_path}: {type(read.error).__name__}: {read.error}"
        )
    parsed = parse(text=read)
    if isinstance(parsed, JsoncFailure):
        return _refusal(detail=f"{config_path} does not parse: {parsed.detail}")
    if not isinstance(parsed, dict):
        return _refusal(detail=f"{config_path} root is not an object")
    return _policy_from_root(root=cast("dict[str, object]", parsed), config_path=config_path)


def workflow_git_author_error(*, committed_text: str, author: GitAuthor) -> str | None:
    """Return a conflict diagnostic for a committed workflow author."""
    sections = tuple(_AUTHOR_SECTION_RE.finditer(committed_text))
    if sections == ():
        return None
    if len(sections) != 1:
        return "workflow declares [run.git.author] more than once"
    body = sections[0].group("body")
    configured_name = _toml_string(body=body, key="name")
    configured_email = _toml_string(body=body, key="email")
    if configured_name is None or configured_email is None:
        return "workflow [run.git.author] must declare non-empty name and email strings"
    configured = GitAuthor(name=configured_name, email=configured_email)
    if configured == author:
        return None
    return (
        "workflow [run.git.author] conflicts with the repository git_author declaration: "
        f"workflow has {configured.name} <{configured.email}>; repository declares "
        f"{author.name} <{author.email}>"
    )


def apply_workflow_git_author(*, committed_text: str, author: GitAuthor) -> str:
    """Add the resolved run author unless an identical section already exists."""
    if _AUTHOR_SECTION_RE.search(committed_text) is not None:
        return committed_text
    separator = "" if committed_text.endswith("\n") else "\n"
    return (
        committed_text
        + separator
        + "\n# --- Dispatcher-resolved operator author for all Fabro commits ---\n"
        + "[run.git.author]\n"
        + f"name = {json.dumps(author.name)}\n"
        + f"email = {json.dumps(author.email)}\n"
    )


def git_author_env_lines(*, author: GitAuthor | None) -> str:
    """Project the resolved pair for the workflow's emergency shell commit."""
    if author is None:
        return ""
    return (
        f"LIVESPEC_GIT_AUTHOR_NAME = {json.dumps(author.name)}\n"
        f"LIVESPEC_GIT_AUTHOR_EMAIL = {json.dumps(author.email)}\n"
    )


def resolve_workflow_git_author(*, committed_text: str, author: GitAuthor | None) -> str | None:
    """Apply an optional resolved author, refusing a conflicting declaration."""
    if author is None:
        return committed_text
    if workflow_git_author_error(committed_text=committed_text, author=author) is not None:
        return None
    return apply_workflow_git_author(committed_text=committed_text, author=author)


def _policy_from_root(*, root: Mapping[str, object], config_path: Path) -> GitAuthorPolicy | str:
    raw_policy = root.get(_POLICY_KEY)
    if not isinstance(raw_policy, dict):
        return _refusal(detail=f"{config_path} must declare {_POLICY_KEY} as an object")
    block = cast("dict[str, object]", raw_policy)
    unknown = tuple(sorted(set(block) - _POLICY_KEYS))
    if unknown:
        return _refusal(
            detail=f"{config_path} {_POLICY_KEY} has unknown keys: {', '.join(unknown)}"
        )
    operator = _author_from(
        raw_name=block.get("operator_name"),
        raw_email=block.get("operator_email"),
    )
    if operator is None:
        return _refusal(
            detail=(
                f"{config_path} {_POLICY_KEY} must declare non-empty operator_name and "
                "operator_email strings"
            )
        )
    mechanical = _mechanical_authors(raw=block.get("mechanical_authors", []))
    if isinstance(mechanical, str):
        return _refusal(detail=f"{config_path} {_POLICY_KEY}.{mechanical}")
    if operator in mechanical:
        return _refusal(
            detail=f"{config_path} classifies its operator pair as a mechanical author too"
        )
    return GitAuthorPolicy(operator=operator, mechanical_authors=mechanical)


def _mechanical_authors(*, raw: object) -> tuple[GitAuthor, ...] | str:
    if not isinstance(raw, list):
        return "mechanical_authors must be an array"
    authors: list[GitAuthor] = []
    for index, raw_author in enumerate(cast("list[object]", raw)):
        if not isinstance(raw_author, dict):
            return f"mechanical_authors[{index}] must be an object"
        entry = cast("dict[str, object]", raw_author)
        if frozenset(entry) != _MECHANICAL_KEYS:
            return f"mechanical_authors[{index}] must contain exactly name and email"
        author = _author_from(raw_name=entry.get("name"), raw_email=entry.get("email"))
        if author is None:
            return f"mechanical_authors[{index}] name and email must be non-empty strings"
        authors.append(author)
    return tuple(authors)


def _author_from(*, raw_name: object, raw_email: object) -> GitAuthor | None:
    if not isinstance(raw_name, str) or not raw_name.strip():
        return None
    if not isinstance(raw_email, str) or not raw_email.strip():
        return None
    return GitAuthor(name=raw_name, email=raw_email)


def _toml_string(*, body: str, key: str) -> str | None:
    match = re.search(
        r"(?m)^" + re.escape(key) + rf"[ \t]*=[ \t]*(?P<value>{_JSON_STRING})[ \t]*$",
        body,
    )
    if match is None:
        return None
    value = cast("str", json.loads(match.group("value")))
    return value if value.strip() else None


def _refusal(*, detail: str) -> str:
    return (
        "Fabro dispatch refused: operator git_author is missing, malformed, or conflicting; "
        f"{detail}"
    )
