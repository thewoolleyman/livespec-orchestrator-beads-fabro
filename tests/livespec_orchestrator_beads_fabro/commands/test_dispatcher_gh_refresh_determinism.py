"""The push helper's support bundle must render identically across clock ticks."""

import hashlib
from unittest.mock import Mock

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    github_auth_support_archive_b64,
)


def test_support_bundle_is_independent_of_the_render_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gzip.time.time", Mock(return_value=100))
    first = github_auth_support_archive_b64()
    monkeypatch.setattr("gzip.time.time", Mock(return_value=200))
    second = github_auth_support_archive_b64()
    assert hashlib.sha256(first.encode()).hexdigest() == hashlib.sha256(second.encode()).hexdigest()
