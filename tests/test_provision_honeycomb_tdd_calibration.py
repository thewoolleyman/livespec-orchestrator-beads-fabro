"""Contracts for the TDD-calibration Honeycomb provisioner.

Plan slice S3 (`bd-ib-3h5vfq`) ships three committed, versioned definitions
and one command that applies them. This file runs that command for real
against a LOCAL API FIXTURE — a stdlib HTTP server implementing the subset of
the Honeycomb management API the command uses — so the create path, the
idempotent update path, the configured thresholds and both refusals are
exercised by execution rather than asserted from the script's text.

The fixture is STRICT about the board wire schema, and that strictness is the
repair `bd-ib-4yvurp` carries. The previous fixture accepted whatever board
payload it was handed, so the legacy shape — one `/1/boards` POST carrying
INLINE query specifications under a top-level `queries` array — passed the
hermetic tier and read as proof, while the current Create a Board API accepts
only `type: "flexible"` boards whose query panels reference PERSISTED query
identifiers. `_FakeHoneycomb.rejection` now refuses an inline board query, an
unsupported top-level field, a missing or unknown `query_id`, and a
`query_annotation_id` that does not apply to its panel's query, so the old
false-positive cannot recur.

What this still CANNOT establish, stated plainly so nobody reads it as more
than it is: the fixture accepts the payload shapes the command sends, so these
tests prove the command is internally consistent, idempotent and conformant to
the DOCUMENTED wire contract, NOT that the live Honeycomb API accepts those
shapes or parses the derived-column expressions. Plan child `bd-ib-i56nut`
owns the live leg and the production resource ids.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from collections.abc import Iterator
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from typing_extensions import override

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "orchestrator-image" / "provision-honeycomb-tdd-calibration.sh"
_DEFINITIONS = _REPO_ROOT / "orchestrator-image" / "honeycomb"
_BOARD_DEFINITION = _DEFINITIONS / "tdd-calibration-board.json"

_RECIPIENT_ID = "recipient-1"
_RECIPIENT_EMAIL = "operator@example.test"
_API_KEY = "not-a-real-key"
_DATASET = "livespec-dispatcher"
_PANEL_COUNT = 7
# A Query cannot be listed, fetched or updated through the API, so the only
# observable record of WHICH specification a persisted query id holds is the
# digest the provisioner writes into that query's annotation. The marker is
# part of the committed contract — `panel_identity_key` in the board
# definition's `livespec` block states it — so a test may name it.
_FINGERPRINT_MARKER = "query-spec-fingerprint="

# The documented Create a Board request body. Anything else is a legacy shape
# or a typo, and the fixture refuses both rather than storing them.
_BOARD_FIELDS = frozenset(
    {
        "name",
        "description",
        "type",
        "panels",
        "layout_generation",
        "tags",
        "preset_filters",
    }
)
# The documented query-panel body. `query` is deliberately ABSENT: a panel
# carrying an inline specification is exactly the defect under repair.
_QUERY_PANEL_FIELDS = frozenset(
    {
        "query_id",
        "query_annotation_id",
        "query_style",
        "visualization_settings",
    }
)
_IDENTITY_FIELDS = {
    "derived_columns": "alias",
    "boards": "name",
    "triggers": "name",
    "query_annotations": "name",
}
_DATASET_KINDS = frozenset({"derived_columns", "triggers", "queries", "query_annotations"})
_GLOBAL_KINDS = frozenset({"boards"})
# `$name` and `$"name"` are the two documented derived-column reference forms.
_COLUMN_REFERENCE = re.compile(r'\$(?:"([^"]+)"|([A-Za-z0-9_.]+))')


class _FakeHoneycomb:
    """The subset of the Honeycomb management API the provisioner drives.

    Holds the three identity-keyed resources the provisioner looks up — derived
    columns by `alias`, boards and triggers by `name` — plus the two
    collections that make up a flexible board's panel substrate: persisted
    queries and the query annotations that name them.

    The write ledgers are SPLIT rather than pooled. `creates`/`updates` cover
    the three identity-keyed resources, and queries and annotations get their
    own lists, so a test can assert that re-applying created no second board
    AND that it created no eighth query annotation — two independent
    populations, which one pooled counter could not distinguish.
    """

    def __init__(self) -> None:
        self.derived_columns: dict[str, dict[str, Any]] = {}
        self.boards: dict[str, dict[str, Any]] = {}
        self.triggers: dict[str, dict[str, Any]] = {}
        self.queries: dict[str, dict[str, Any]] = {}
        self.query_annotations: dict[str, dict[str, Any]] = {}
        self.creates: list[str] = []
        self.updates: list[str] = []
        self.query_creates: list[str] = []
        self.annotation_creates: list[str] = []
        self.annotation_updates: list[str] = []
        # Every write's dataset segment, so a test can prove the configured
        # dataset reached the URL rather than trusting the payload.
        self.write_datasets: list[str] = []
        # Columns this account does NOT have. A derived-column expression
        # referencing one 400s with the detail the live API was measured to
        # return, which is the arm the diagnostic control drives.
        self.unknown_columns: frozenset[str] = frozenset()
        self._next_id = 0
        self._lock = threading.Lock()

    def collection(self, *, kind: str) -> dict[str, dict[str, Any]]:
        return {
            "derived_columns": self.derived_columns,
            "boards": self.boards,
            "triggers": self.triggers,
            "queries": self.queries,
            "query_annotations": self.query_annotations,
        }[kind]

    def create(self, *, kind: str, dataset: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._next_id += 1
            record = {**payload, "id": f"{kind}-{self._next_id}"}
            self.collection(kind=kind)[record["id"]] = record
            self.write_datasets.append(f"{kind}:{dataset}")
            self._create_ledger(kind=kind).append(self._label(kind=kind, record=record))
            return record

    def update(self, *, kind: str, resource_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            record = {**payload, "id": resource_id}
            self.collection(kind=kind)[resource_id] = record
            self._update_ledger(kind=kind).append(self._label(kind=kind, record=record))
            return record

    def rejection(self, *, kind: str, payload: dict[str, Any]) -> str | None:
        """Return the 400 detail for an unusable payload, or None to accept it."""
        return {
            "boards": self._board_detail,
            "derived_columns": self._derived_column_detail,
            "query_annotations": self._annotation_detail,
        }.get(kind, _accepts)(payload=payload)

    def _label(self, *, kind: str, record: dict[str, Any]) -> str:
        field = _IDENTITY_FIELDS.get(kind)
        return f"{kind}:{record[field]}" if field else f"{kind}:{record['id']}"

    def _create_ledger(self, *, kind: str) -> list[str]:
        return {
            "queries": self.query_creates,
            "query_annotations": self.annotation_creates,
        }.get(kind, self.creates)

    def _update_ledger(self, *, kind: str) -> list[str]:
        return {"query_annotations": self.annotation_updates}.get(kind, self.updates)

    def _board_detail(self, *, payload: dict[str, Any]) -> str | None:
        unsupported = sorted(set(payload) - _BOARD_FIELDS)
        panels = payload.get("panels") or []
        checks = (
            (bool(unsupported), f"unsupported board fields: {', '.join(unsupported)}"),
            (
                payload.get("type") != "flexible",
                f"type must be flexible, got {payload.get('type')!r}",
            ),
            (not panels, "a board must carry at least one panel"),
        )
        detail = next((text for failed, text in checks if failed), None)
        if detail is not None:
            return detail
        panel_details = (
            self._panel_detail(index=index, panel=panel) for index, panel in enumerate(panels)
        )
        return next((text for text in panel_details if text is not None), None)

    def _panel_detail(self, *, index: int, panel: dict[str, Any]) -> str | None:
        query_panel = panel.get("query_panel") or {}
        unsupported = sorted(set(query_panel) - _QUERY_PANEL_FIELDS)
        query_id = query_panel.get("query_id") or ""
        annotation_id = query_panel.get("query_annotation_id") or ""
        annotation = self.query_annotations.get(annotation_id)
        checks = (
            (panel.get("type") != "query", f"panels[{index}].type must be query"),
            (
                bool(unsupported),
                f"panels[{index}].query_panel carries unsupported fields: "
                f"{', '.join(unsupported)}",
            ),
            (not query_id, f"panels[{index}].query_panel.query_id is required"),
            (
                bool(query_id) and query_id not in self.queries,
                f"panels[{index}].query_panel.query_id {query_id!r} does not exist",
            ),
            (
                bool(annotation_id) and annotation is None,
                f"panels[{index}].query_panel.query_annotation_id {annotation_id!r} "
                "does not exist",
            ),
            (
                annotation is not None and annotation.get("query_id") != query_id,
                f"panels[{index}] annotation {annotation_id!r} does not apply to "
                f"query {query_id!r}",
            ),
        )
        return next((text for failed, text in checks if failed), None)

    def _derived_column_detail(self, *, payload: dict[str, Any]) -> str | None:
        referenced = {
            match.group(1) or match.group(2)
            for match in _COLUMN_REFERENCE.finditer(str(payload.get("expression", "")))
        }
        missing = sorted(referenced & self.unknown_columns)
        return f"unknown column name: {missing[0]}" if missing else None

    def _annotation_detail(self, *, payload: dict[str, Any]) -> str | None:
        query_id = payload.get("query_id") or ""
        checks = (
            (not payload.get("name"), "query annotation name is required"),
            (not query_id, "query annotation query_id is required"),
            (
                bool(query_id) and query_id not in self.queries,
                f"query annotation query_id {query_id!r} does not exist",
            ),
        )
        return next((text for failed, text in checks if failed), None)


def _accepts(*, payload: dict[str, Any]) -> str | None:
    """Accept any payload — the fixture models no constraint for this kind."""
    _ = payload
    return None


_RECIPIENTS_BODY = [
    {"id": _RECIPIENT_ID, "type": "email", "details": {"email_address": _RECIPIENT_EMAIL}}
]


def _route(*, path: str) -> tuple[str, str, str] | None:
    """Resolve a request path to `(collection kind, dataset, resource id)`.

    `/1/boards` carries no dataset segment while every other collection does,
    so the two shapes are resolved separately rather than by counting depth and
    hoping. An empty resource id means the path names the whole collection.
    """
    parts = [part for part in path.split("/") if part]
    if len(parts) < 2 or parts[0] != "1":
        return None
    kind = parts[1]
    if kind in _GLOBAL_KINDS:
        if len(parts) == 2:
            return kind, "", ""
        return (kind, "", parts[2]) if len(parts) == 3 else None
    if kind not in _DATASET_KINDS or len(parts) < 3:
        return None
    if len(parts) == 3:
        return kind, parts[2], ""
    return (kind, parts[2], parts[3]) if len(parts) == 4 else None


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
        if resolved is None or (self.command == "PUT" and resolved[2] == ""):
            self._reply(status=HTTPStatus.NOT_FOUND, body={"error": self.path})
            return
        kind, dataset, resource_id = resolved
        if self.command == "GET":
            self._reply(status=HTTPStatus.OK, body=list(self._api().collection(kind=kind).values()))
            return
        payload = self._payload()
        detail = self._api().rejection(kind=kind, payload=payload)
        if detail is not None:
            self._reply(
                status=HTTPStatus.BAD_REQUEST,
                body={"error": "unable to process request", "detail": detail},
            )
            return
        self._write(kind=kind, dataset=dataset, resource_id=resource_id, payload=payload)

    def _write(self, *, kind: str, dataset: str, resource_id: str, payload: dict[str, Any]) -> None:
        if self.command == "POST":
            self._reply(
                status=HTTPStatus.CREATED,
                body=self._api().create(kind=kind, dataset=dataset, payload=payload),
            )
            return
        self._reply(
            status=HTTPStatus.OK,
            body=self._api().update(kind=kind, resource_id=resource_id, payload=payload),
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
        "HONEYCOMB_CONFIG_KEY_LIVESPEC": _API_KEY,
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


def _post(*, api_base: str, path: str, payload: dict[str, Any]) -> int:
    """POST a payload straight at the fixture, returning its status code."""
    request = Request(  # noqa: S310 — the local test fixture.
        f"{api_base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5.0) as response:  # noqa: S310 — the local test fixture.
        return int(response.status)


def _committed_panels() -> list[dict[str, Any]]:
    document = json.loads(_BOARD_DEFINITION.read_text(encoding="utf-8"))
    return list(document["payload"]["panels"])


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
        assert meta["dataset"] == _DATASET
        # The live leg is carried by a named dependent child, and each
        # definition says so rather than implying it was already applied.
        assert "bd-ib-i56nut" in meta["live_validation_owed"]


def test_the_board_groups_the_share_by_repository_and_adapter() -> None:
    panels = _committed_panels()
    queries = [panel["query_panel"]["query"] for panel in panels]
    breakdowns = {tuple(query.get("breakdowns", ())) for query in queries}

    assert ("repo",) in breakdowns
    assert ("livespec.implement.adapter",) in breakdowns
    # Every share query excludes the unclassifiable population: counting it
    # would let a dropped signal read as a healthy run.
    share_queries = [
        query
        for query in queries
        if any(
            calculation.get("column") == "tdd_post_hoc_red_flag"
            for calculation in query["calculations"]
        )
    ]
    assert share_queries
    for query in share_queries:
        assert {
            "column": "tdd_post_hoc_red",
            "op": "!=",
            "value": "unknown",
        } in query["filters"]


def test_every_committed_panel_is_a_query_panel_with_a_caption_and_a_position() -> None:
    panels = _committed_panels()

    assert len(panels) == _PANEL_COUNT
    assert all(panel["type"] == "query" for panel in panels)
    captions = [panel["query_panel"]["caption"] for panel in panels]
    assert len(set(captions)) == _PANEL_COUNT, "a caption is the panel's stable identity"
    # A deterministic, readable layout: every panel names its own slot, and no
    # two panels occupy the same one.
    slots = [
        (panel["position"]["x_coordinate"], panel["position"]["y_coordinate"]) for panel in panels
    ]
    assert len(set(slots)) == _PANEL_COUNT
    assert all(panel["position"]["height"] > 0 for panel in panels)
    assert all(panel["position"]["width"] > 0 for panel in panels)


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
    still_present = {
        record["id"]
        for collection in (api.derived_columns, api.boards, api.triggers)
        for record in collection.values()
    }
    assert still_present == created_ids


def test_reapplying_preserves_every_identifier_without_duplicating_panels(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    """Acceptance assertion 2 — a re-apply updates, it does not accumulate.

    The board, the two derived columns and the trigger are looked up by their
    stable identity, so their ids survive. The panels are the hard half: a
    Query has no list, get or update verb, so re-applying would persist seven
    NEW queries and attach seven NEW annotations unless the provisioner
    recognises the ones already there.
    """
    api, api_base = honeycomb

    first = _run(api_base=api_base)
    assert first.returncode == 0, first.stderr
    identifiers = (
        set(api.boards),
        set(api.derived_columns),
        set(api.triggers),
        set(api.queries),
        set(api.query_annotations),
    )
    first_board = next(iter(api.boards.values()))
    panels_before = [panel["query_panel"] for panel in first_board["panels"]]
    assert len(api.query_annotations) == _PANEL_COUNT
    assert all(
        _FINGERPRINT_MARKER in record["description"] for record in api.query_annotations.values()
    )

    second = _run(api_base=api_base)

    assert second.returncode == 0, second.stderr
    assert (
        set(api.boards),
        set(api.derived_columns),
        set(api.triggers),
        set(api.queries),
        set(api.query_annotations),
    ) == identifiers
    # No duplicate panels and no duplicate annotations: the second run reused
    # every persisted query and updated each annotation in place.
    assert len(api.queries) == _PANEL_COUNT
    assert len(api.query_annotations) == _PANEL_COUNT
    assert len(api.annotation_creates) == _PANEL_COUNT
    assert len(api.annotation_updates) == _PANEL_COUNT
    assert len(api.query_creates) == _PANEL_COUNT
    board = next(iter(api.boards.values()))
    assert [panel["query_panel"] for panel in board["panels"]] == panels_before
    assert "reused query" in second.stdout
    assert "updated query_annotation" in second.stdout


def test_a_moved_specification_repoints_the_same_annotation_at_a_fresh_query(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    """Reuse must be CONDITIONAL on the specification, not unconditional.

    Pre-seed the annotation a panel would match — right name, stale
    fingerprint, pointing at some other query. Blind reuse would leave the
    board rendering that stale query forever, which is the failure mode an
    idempotence rule can hide. The provisioner must persist a fresh query and
    re-point the SAME annotation at it, so the identifier survives while the
    content moves.
    """
    api, api_base = honeycomb
    caption = _committed_panels()[0]["query_panel"]["caption"]
    stale_query = api.create(
        kind="queries", dataset=_DATASET, payload={"calculations": [{"op": "COUNT"}]}
    )
    stale = api.create(
        kind="query_annotations",
        dataset=_DATASET,
        payload={
            "name": caption,
            "description": f"{_FINGERPRINT_MARKER}0000000000000000",
            "query_id": stale_query["id"],
        },
    )

    result = _run(api_base=api_base, overrides={"HONEYCOMB_TDD_RESOURCES": "board"})

    assert result.returncode == 0, result.stderr
    assert len(api.query_annotations) == _PANEL_COUNT, "the stale annotation was reused"
    assert stale["id"] in api.query_annotations
    refreshed = api.query_annotations[stale["id"]]
    assert refreshed["query_id"] != stale_query["id"]
    assert refreshed["query_id"] in api.queries
    assert f"{_FINGERPRINT_MARKER}0000000000000000" not in refreshed["description"]
    first_panel = next(iter(api.boards.values()))["panels"][0]["query_panel"]
    assert first_panel["query_annotation_id"] == stale["id"]
    assert first_panel["query_id"] == refreshed["query_id"]


def test_the_board_is_flexible_and_its_panels_reference_persisted_queries(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    """Acceptance assertion 1 — the shipped provisioner builds a usable board.

    The old command POSTed `board.payload` straight at `/1/boards` with its
    query specifications inline. The current API takes a flexible board whose
    panels name PERSISTED queries, so the command must materialize each
    committed specification through the Queries API first and then reference
    the ids it got back.
    """
    api, api_base = honeycomb

    result = _run(api_base=api_base, overrides={"HONEYCOMB_TDD_RESOURCES": "board"})

    assert result.returncode == 0, result.stderr
    board = next(iter(api.boards.values()))
    assert board["type"] == "flexible"
    panels = board["panels"]
    assert len(panels) == _PANEL_COUNT
    # Each panel names a query the Queries API persisted — and ONLY that, since
    # the fixture refuses a panel carrying an inline specification at all.
    referenced = [panel["query_panel"]["query_id"] for panel in panels]
    assert set(referenced) == set(api.queries)
    assert len(set(referenced)) == _PANEL_COUNT
    # The captions survive as the query annotations the panels point at, in the
    # committed order.
    annotated = [
        api.query_annotations[panel["query_panel"]["query_annotation_id"]]["name"]
        for panel in panels
    ]
    assert annotated == [panel["query_panel"]["caption"] for panel in _committed_panels()]
    # Every persisted query went to the configured dataset.
    assert {entry for entry in api.write_datasets if entry.startswith("queries:")} == {
        f"queries:{_DATASET}"
    }


def test_the_persisted_queries_retain_the_committed_calculations_and_filters(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    api, api_base = honeycomb

    result = _run(api_base=api_base, overrides={"HONEYCOMB_TDD_RESOURCES": "board"})

    assert result.returncode == 0, result.stderr
    persisted = [
        {key: value for key, value in record.items() if key != "id"}
        for record in api.queries.values()
    ]
    committed = [panel["query_panel"]["query"] for panel in _committed_panels()]
    assert persisted == committed
    breakdowns = {tuple(record.get("breakdowns", ())) for record in persisted}
    assert ("repo",) in breakdowns
    assert ("livespec.implement.adapter",) in breakdowns
    assert ("repo", "livespec.implement.adapter") in breakdowns


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


# --- the fixture's own controls --------------------------------------------


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


def test_the_fixture_refuses_the_legacy_board_with_inline_queries(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    """The negative control that makes the whole tier meaningful.

    This is the payload the command used to send: a `visual` board carrying a
    top-level `queries` array of inline specifications. The previous fixture
    stored it and reported success, so the hermetic tier passed on a board the
    live API cannot create. It must now 400.
    """
    _api, api_base = honeycomb
    legacy = {
        "name": "legacy inline board",
        "style": "visual",
        "column_layout": "multi",
        "queries": [
            {
                "caption": "inline",
                "dataset": _DATASET,
                "query_style": "graph",
                "query": {"calculations": [{"op": "COUNT"}], "time_range": 604800},
            }
        ],
    }

    with pytest.raises(HTTPError) as refused:
        _ = _post(api_base=api_base, path="/1/boards", payload=legacy)

    assert refused.value.code == HTTPStatus.BAD_REQUEST
    detail = json.loads(refused.value.read().decode("utf-8"))["detail"]
    assert "queries" in detail
    assert "unsupported board fields" in detail


def test_the_fixture_refuses_a_panel_whose_query_id_is_absent_or_unknown(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    _api, api_base = honeycomb
    position = {"x_coordinate": 0, "y_coordinate": 0, "width": 6, "height": 4}

    def board(*, query_panel: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": "probe",
            "type": "flexible",
            "panels": [{"type": "query", "position": position, "query_panel": query_panel}],
        }

    with pytest.raises(HTTPError) as missing:
        _ = _post(api_base=api_base, path="/1/boards", payload=board(query_panel={}))
    assert missing.value.code == HTTPStatus.BAD_REQUEST
    assert "query_id is required" in json.loads(missing.value.read().decode("utf-8"))["detail"]

    with pytest.raises(HTTPError) as unknown:
        _ = _post(
            api_base=api_base,
            path="/1/boards",
            payload=board(query_panel={"query_id": "queries-404"}),
        )
    assert unknown.value.code == HTTPStatus.BAD_REQUEST
    assert "does not exist" in json.loads(unknown.value.read().decode("utf-8"))["detail"]


def test_the_dry_run_mode_prints_every_payload_and_calls_nothing(
    honeycomb: tuple[_FakeHoneycomb, str],
) -> None:
    api, api_base = honeycomb

    result = _run(api_base=api_base, overrides={"DRY_RUN": "1"})

    assert result.returncode == 0
    assert api.creates == []
    assert api.updates == []
    assert api.query_creates == []
    assert api.annotation_creates == []
    # Two derived columns, one board, one trigger, plus the seven queries and
    # seven query annotations the board's panels are built from.
    assert result.stdout.count("DRY_RUN") == 4 + (2 * _PANEL_COUNT)
    assert "tdd_post_hoc_red_flag" in result.stdout
