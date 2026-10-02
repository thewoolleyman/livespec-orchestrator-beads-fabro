"""Contracts for the TDD-calibration Honeycomb provisioner.

Plan slice S3 (`bd-ib-3h5vfq`) ships three committed, versioned definitions
and one command that applies them. This file runs that command for real
against a LOCAL API FIXTURE — a stdlib HTTP server implementing the subset of
the Honeycomb management API the command uses — so the create path, the
idempotent update path, the configured thresholds and both refusals are
exercised by execution rather than asserted from the script's text.

What this CANNOT establish, stated plainly so nobody reads it as more than it
is: the fixture accepts the payload shapes the command sends, so these tests
prove the command is internally consistent and idempotent, NOT that the live
Honeycomb API accepts those shapes or parses the derived-column expressions.
Plan child `bd-ib-i56nut` owns the live leg and the production resource ids.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Iterator
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest
from typing_extensions import override

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "orchestrator-image" / "provision-honeycomb-tdd-calibration.sh"
_DEFINITIONS = _REPO_ROOT / "orchestrator-image" / "honeycomb"

_RECIPIENT_ID = "recipient-1"
_RECIPIENT_EMAIL = "operator@example.test"


class _FakeHoneycomb:
    """The subset of the Honeycomb management API the provisioner drives.

    Holds three collections keyed by their stable identity — derived columns by
    `alias`, boards and triggers by `name` — and records every write so a test
    can tell a CREATE from an UPDATE. That distinction is the whole point: an
    idempotent provisioner must create on the first run and update on the
    second, and a command that created twice would look identical from the
    outside without this ledger.
    """

    def __init__(self) -> None:
        self.derived_columns: dict[str, dict[str, Any]] = {}
        self.boards: dict[str, dict[str, Any]] = {}
        self.triggers: dict[str, dict[str, Any]] = {}
        self.creates: list[str] = []
        self.updates: list[str] = []
        self._next_id = 0
        self._lock = threading.Lock()

    def collection(self, *, kind: str) -> dict[str, dict[str, Any]]:
        return {
            "derived_columns": self.derived_columns,
            "boards": self.boards,
            "triggers": self.triggers,
        }[kind]

    def identity_field(self, *, kind: str) -> str:
        return "alias" if kind == "derived_columns" else "name"

    def create(self, *, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._next_id += 1
            record = {**payload, "id": f"{kind}-{self._next_id}"}
            self.collection(kind=kind)[record["id"]] = record
            self.creates.append(f"{kind}:{payload[self.identity_field(kind=kind)]}")
            return record

    def update(self, *, kind: str, resource_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            record = {**payload, "id": resource_id}
            self.collection(kind=kind)[resource_id] = record
            self.updates.append(f"{kind}:{payload[self.identity_field(kind=kind)]}")
            return record


_COLLECTION_KINDS = frozenset({"derived_columns", "boards", "triggers"})
_RECIPIENTS_BODY = [
    {"id": _RECIPIENT_ID, "type": "email", "details": {"email_address": _RECIPIENT_EMAIL}}
]


def _route(*, path: str) -> tuple[str, str] | None:
    """Resolve a request path to `(collection kind, resource id)`, or None.

    `/1/boards` carries no dataset segment while the other two collections do,
    so the depth that means "this names one resource" differs per kind. An
    empty resource id means the path names the whole collection.
    """
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2 or parts[0] != "1" or parts[1] not in _COLLECTION_KINDS:
        return None
    kind = parts[1]
    return kind, parts[-1] if len(parts) == (3 if kind == "boards" else 4) else ""


class _FixtureServer(ThreadingHTTPServer):
    """The fixture HTTP server, carrying the API state its handler reads.

    The state hangs off the SERVER rather than off a closure so the handler
    class lives at module level: a handler built inside a factory re-declares
    three dispatch methods per instantiation, which reads as one deeply nested
    function to every complexity measure.
    """

    api: _FakeHoneycomb = _FakeHoneycomb()


class _Handler(BaseHTTPRequestHandler):
    """One handler for all three verbs, dispatched on `self.command`.

    The stdlib would take three `do_<VERB>` methods; routing is identical
    across them and only the write differs, so they share one body and the
    verb selects the effect.
    """

    protocol_version = "HTTP/1.1"

    @override
    def log_message(self, format: str, *args: object) -> None:
        """Silence the per-request stderr line the stdlib handler prints."""

    def _api(self) -> _FakeHoneycomb:
        return cast("_FixtureServer", self.server).api

    def _reply(self, *, status: HTTPStatus, body: object) -> None:
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        _ = self.wfile.write(encoded)

    def _payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _handle(self) -> None:
        if self.path == "/1/recipients":
            self._reply(status=HTTPStatus.OK, body=_RECIPIENTS_BODY)
            return
        resolved = _route(path=self.path)
        if resolved is None or (self.command == "PUT" and resolved[1] == ""):
            self._reply(status=HTTPStatus.NOT_FOUND, body={"error": self.path})
            return
        kind, resource_id = resolved
        if self.command == "GET":
            self._reply(status=HTTPStatus.OK, body=list(self._api().collection(kind=kind).values()))
        elif self.command == "POST":
            self._reply(
                status=HTTPStatus.CREATED,
                body=self._api().create(kind=kind, payload=self._payload()),
            )
        else:
            self._reply(
                status=HTTPStatus.OK,
                body=self._api().update(
                    kind=kind, resource_id=resource_id, payload=self._payload()
                ),
            )

    def do_GET(self) -> None:  # noqa: N802 — stdlib dispatch name.
        self._handle()

    def do_POST(self) -> None:  # noqa: N802 — stdlib dispatch name.
        self._handle()

    def do_PUT(self) -> None:  # noqa: N802 — stdlib dispatch name.
        self._handle()


@pytest.fixture
def honeycomb() -> Iterator[tuple[_FakeHoneycomb, str]]:
    """A running local API fixture and its base URL."""
    api = _FakeHoneycomb()
    server = _FixtureServer(("127.0.0.1", 0), _Handler)
    server.api = api
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield api, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


def _run(
    *, api_base: str, overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "HONEYCOMB_API_BASE": api_base,
        "HONEYCOMB_CONFIG_KEY_LIVESPEC": "not-a-real-key",
        "HONEYCOMB_OPERATOR_ALERT_RECIPIENT": _RECIPIENT_EMAIL,
    }
    _ = env.pop("DRY_RUN", None)
    for key, value in (overrides or {}).items():
        # An override of "" means UNSET, so a test can drive the arm where a
        # variable is absent rather than merely blank.
        if value == "":
            _ = env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        check=False,
        env=env,
        text=True,
        capture_output=True,
    )


# --- the committed definitions ---------------------------------------------


def test_every_definition_is_versioned_committed_json() -> None:
    for name in (
        "tdd-calibration-derived-columns.json",
        "tdd-calibration-board.json",
        "tdd-calibration-trigger.json",
    ):
        document = json.loads((_DEFINITIONS / name).read_text(encoding="utf-8"))
        meta = document["livespec"]
        assert meta["definition_version"] >= 1
        assert meta["work_item"] == "bd-ib-3h5vfq"
        assert meta["dataset"] == "livespec-dispatcher"
        # The live leg is carried by a named dependent child, and each
        # definition says so rather than implying it was already applied.
        assert "bd-ib-i56nut" in meta["live_validation_owed"]


def test_the_board_groups_the_share_by_repository_and_adapter() -> None:
    document = json.loads((_DEFINITIONS / "tdd-calibration-board.json").read_text(encoding="utf-8"))
    queries = document["payload"]["queries"]
    breakdowns = {tuple(query["query"].get("breakdowns", ())) for query in queries}

    assert ("repo",) in breakdowns
    assert ("livespec.implement.adapter",) in breakdowns
    assert all(query["dataset"] == "livespec-dispatcher" for query in queries)
    # Every share query excludes the unclassifiable population: counting it
    # would let a dropped signal read as a healthy run.
    share_queries = [
        query
        for query in queries
        if any(
            calculation.get("column") == "tdd_post_hoc_red_flag"
            for calculation in query["query"]["calculations"]
        )
    ]
    assert share_queries
    for query in share_queries:
        assert {
            "column": "tdd_post_hoc_red",
            "op": "!=",
            "value": "unknown",
        } in query["query"]["filters"]


# --- provisioning, against the local fixture -------------------------------


def test_a_first_run_creates_every_resource(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    api, api_base = honeycomb

    result = _run(api_base=api_base)

    assert result.returncode == 0, result.stderr
    assert api.creates == [
        "derived_columns:tdd_post_hoc_red",
        "derived_columns:tdd_post_hoc_red_flag",
        "boards:livespec factory test-first order (TDD calibration)",
        "triggers:livespec factory post-hoc Red share",
    ]
    assert api.updates == []
    assert "created derived_column" in result.stdout
    assert "created board" in result.stdout
    assert "created trigger" in result.stdout


def test_a_second_run_updates_in_place_and_creates_nothing(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    api, api_base = honeycomb

    first = _run(api_base=api_base)
    assert first.returncode == 0, first.stderr
    created_ids = {
        record["id"]
        for collection in (api.derived_columns, api.boards, api.triggers)
        for record in collection.values()
    }

    second = _run(api_base=api_base)

    assert second.returncode == 0, second.stderr
    assert len(api.creates) == 4, "the second run must not create a duplicate resource"
    assert len(api.updates) == 4
    assert "updated derived_column" in second.stdout
    assert "created" not in second.stdout
    still_present = {
        record["id"]
        for collection in (api.derived_columns, api.boards, api.triggers)
        for record in collection.values()
    }
    assert still_present == created_ids


def test_the_trigger_carries_the_resolved_recipient_and_configured_threshold(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    api, api_base = honeycomb

    result = _run(
        api_base=api_base,
        overrides={
            "HONEYCOMB_TDD_POST_HOC_SHARE_THRESHOLD": "0.4",
            "HONEYCOMB_TDD_TRIGGER_WINDOW_SECONDS": "43200",
            "HONEYCOMB_TDD_TRIGGER_FREQUENCY_SECONDS": "3600",
        },
    )

    assert result.returncode == 0, result.stderr
    trigger = next(iter(api.triggers.values()))
    assert trigger["recipients"] == [{"id": _RECIPIENT_ID}]
    assert trigger["threshold"] == {"op": ">=", "value": 0.4, "exceeded_limit": 1}
    assert trigger["frequency"] == 3600
    assert trigger["query"]["time_range"] == 43200
    # The operator-facing description states the threshold that fired and what
    # to do about it, rather than leaving the reader to look the value up.
    assert "40%" in trigger["description"]
    assert "WHAT TO DO" in trigger["description"]


def test_the_gap_threshold_is_configurable_into_the_derived_column_expression(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    api, api_base = honeycomb

    result = _run(api_base=api_base, overrides={"HONEYCOMB_TDD_POST_HOC_GAP_SECONDS": "300"})

    assert result.returncode == 0, result.stderr
    expressions = [record["expression"] for record in api.derived_columns.values()]
    assert expressions
    for expression in expressions:
        assert "300" in expression
        assert "__GAP_SECONDS__" not in expression
    classification = next(
        record for record in api.derived_columns.values() if record["alias"] == "tdd_post_hoc_red"
    )
    assert "tdd.first_product_write_before_red" in classification["expression"]
    assert "tdd.red_green_gap_seconds_median" in classification["expression"]


def test_one_resource_can_be_applied_without_touching_the_others(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    api, api_base = honeycomb

    result = _run(api_base=api_base, overrides={"HONEYCOMB_TDD_RESOURCES": "board"})

    assert result.returncode == 0, result.stderr
    assert api.creates == ["boards:livespec factory test-first order (TDD calibration)"]
    assert api.derived_columns == {}
    assert api.triggers == {}


# --- refusals --------------------------------------------------------------


def test_a_window_shorter_than_the_evaluation_frequency_is_refused_with_the_fix(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    _api, api_base = honeycomb

    result = _run(
        api_base=api_base,
        overrides={
            "HONEYCOMB_TDD_RESOURCES": "trigger",
            "HONEYCOMB_TDD_TRIGGER_WINDOW_SECONDS": "600",
            "HONEYCOMB_TDD_TRIGGER_FREQUENCY_SECONDS": "7200",
        },
    )

    assert result.returncode != 0
    assert "window (600s) must be >= frequency (7200s)" in result.stderr
    assert "HONEYCOMB_TDD_TRIGGER_WINDOW_SECONDS" in result.stderr


def test_an_unset_recipient_lists_the_discovered_ones_with_emails_redacted(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    _api, api_base = honeycomb

    result = _run(
        api_base=api_base,
        overrides={
            "HONEYCOMB_TDD_RESOURCES": "trigger",
            "HONEYCOMB_OPERATOR_ALERT_RECIPIENT": "",
        },
    )

    assert result.returncode != 0
    assert "HONEYCOMB_OPERATOR_ALERT_RECIPIENT is required." in result.stderr
    assert f"id={_RECIPIENT_ID} type=email" in result.stderr
    assert "o***r@example.test" in result.stderr
    assert _RECIPIENT_EMAIL not in result.stderr


def test_an_unmatched_recipient_selector_is_refused_by_name(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    _api, api_base = honeycomb

    result = _run(
        api_base=api_base,
        overrides={
            "HONEYCOMB_TDD_RESOURCES": "trigger",
            "HONEYCOMB_OPERATOR_ALERT_RECIPIENT": "nobody@example.test",
        },
    )

    assert result.returncode != 0
    assert "no Honeycomb recipient matched 'nobody@example.test'" in result.stderr


def test_a_missing_api_key_is_refused_before_any_call(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    api, api_base = honeycomb

    result = _run(
        api_base=api_base,
        overrides={
            "HONEYCOMB_CONFIG_KEY_LIVESPEC": "",
            "HONEYCOMB_TEAM_KEY_LIVESPEC": "",
        },
    )

    assert result.returncode == 2
    assert "HONEYCOMB_CONFIG_KEY_LIVESPEC is required" in result.stderr
    assert "with-livespec-env.sh" in result.stderr
    assert api.creates == []


def test_the_fixture_refuses_a_path_the_provisioner_never_sends(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    """The fixture's own control: an unrouted path 404s rather than 500s.

    Worth asserting because a silent 500 here would read, from the
    provisioner's side, exactly like a Honeycomb outage — and the first thing
    a future editor does when a request misroutes is ask what the fixture did
    with it.
    """
    _api, api_base = honeycomb

    with pytest.raises(HTTPError) as refused:
        _ = urlopen(f"{api_base}/1/not_a_collection", timeout=5.0)  # noqa: S310 — the local test fixture.

    assert refused.value.code == HTTPStatus.NOT_FOUND


def test_the_dry_run_mode_prints_every_payload_and_calls_nothing(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    api, api_base = honeycomb

    result = _run(api_base=api_base, overrides={"DRY_RUN": "1"})

    assert result.returncode == 0, result.stderr
    assert api.creates == []
    assert api.updates == []
    assert result.stdout.count("DRY_RUN") == 4
    assert "tdd_post_hoc_red_flag" in result.stdout
