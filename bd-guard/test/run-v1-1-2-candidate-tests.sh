#!/usr/bin/env bash
# run-v1-1-2-candidate-tests.sh - qualify the tracked bd guard against the
# official Beads v1.2.2 Linux amd64 binary without installing it.
#
# The harness downloads the release into a temporary directory, verifies the
# immutable O1 tarball, SPDX, extracted-binary, and version evidence, then runs
# bd-guard.sh with LIVESPEC_BD_REAL pointed at that temporary binary. All Beads
# state lives under temporary git repositories and a temporary HOME/XDG_CONFIG_HOME;
# nothing is copied to /usr/local/bin, no production tenant is contacted, and no
# Fabro server or image state is touched.

set -euo pipefail

# NEVER set VERSION to 1.2.0 or 1.2.1. Upstream published both by accident on
# 2026-08-11 without release testing; running the v1.2.1 binary EVEN ONCE
# migrates the schema from v53 to v65, after which every v1.1.2 / v1.2.2 binary
# refuses with "schema version mismatch: database is at v65". We run a SHARED
# multi-tenant Dolt server, so one invocation strands that tenant for the whole
# family. Both are still downloadable (marked prerelease, not withdrawn). The
# current stable is v1.2.2, a recovery release re-issuing the tested 1.1 line.
# This harness never contacts a production tenant, but the prohibition is
# recorded here because this is one of the two places the version is pinned.
# See AGENTS.md "Beads runtime prerequisites".
VERSION="1.2.2"
RELEASE_BASE="https://github.com/gastownhall/beads/releases/download/v${VERSION}"
TARBALL="beads_${VERSION}_linux_amd64.tar.gz"
SPDX="beads-v${VERSION}.spdx.json"
EXPECTED_TARBALL_SHA="8140098a51d3b81d5548d1c5e6db1a2d9930e5d141efe2a4bff7d079c4d321e8"
EXPECTED_BIN_SHA="54fc0e0581ce4c5487a5b242f0a4f34af1ef09cf056e164a1af63a6ec7aa1e0e"
EXPECTED_SPDX_SHA="117f89c22d3562029521b67f1bfcfa7a173513a8cd2c63edf09541dae5d60197"
EXPECTED_VERSION="bd version 1.2.2 (6c124203e: HEAD@6c124203e771)"

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd -P)"
WRAPPER="${SCRIPT_DIR}/../bd-guard.sh"

WORK="$(mktemp -d)"
cleanup() {
    chmod -R u+w "$WORK" 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT

HOME_T="${WORK}/home"
XDG_T="${WORK}/xdg"
mkdir -p "$HOME_T" "$XDG_T"

pass() { printf '  ok:   %s\n' "$1"; }
fail() {
    printf '  FAIL: %s\n' "$1" >&2
    exit 1
}

run_bd() {
    HOME="$HOME_T" \
    XDG_CONFIG_HOME="$XDG_T" \
    BEADS_ACTOR="E2E Test" \
    "$BD" "$@"
}

run_guard() {
    HOME="$HOME_T" \
    XDG_CONFIG_HOME="$XDG_T" \
    BEADS_ACTOR="E2E Test" \
    LIVESPEC_BD_REAL="$BD" \
    LIVESPEC_BD_GUARD_OTLP=off \
    LIVESPEC_BD_GUARD_MODE_FILE="${WORK}/no-such-mode-file" \
    "$WRAPPER" "$@"
}

run_guard_otlp() {
    HOME="$HOME_T" \
    XDG_CONFIG_HOME="$XDG_T" \
    BEADS_ACTOR="E2E Test" \
    LIVESPEC_BD_REAL="$BD" \
    LIVESPEC_BD_GUARD_MODE_FILE="${WORK}/no-such-mode-file" \
    "$WRAPPER" "$@"
}

status_of() {
    python3 - "$1" "$2" <<'PY'
import json
import sys

path, issue_id = sys.argv[1], sys.argv[2]
for item in json.load(open(path, encoding="utf-8")):
    if item["id"] == issue_id:
        print(item["status"])
        raise SystemExit(0)
raise SystemExit(f"missing issue {issue_id}")
PY
}

field_of_object() {
    python3 - "$1" "$2" <<'PY'
import json
import sys

path, field = sys.argv[1], sys.argv[2]
obj = json.load(open(path, encoding="utf-8"))
if isinstance(obj, list):
    obj = obj[0]
print(obj[field])
PY
}

assert_json_array() {
    python3 - "$1" <<'PY'
import json
import sys

obj = json.load(open(sys.argv[1], encoding="utf-8"))
if not isinstance(obj, list):
    raise SystemExit(f"expected list, got {type(obj).__name__}")
PY
}

assert_no_issue() {
    python3 - "$1" "$2" <<'PY'
import json
import sys

path, issue_id = sys.argv[1], sys.argv[2]
items = json.load(open(path, encoding="utf-8"))
raise SystemExit(any(item["id"] == issue_id for item in items))
PY
}

assert_batch_items_stayed_open() {
    python3 - "$1" <<'PY'
import json
import sys

items = json.load(open(sys.argv[1], encoding="utf-8"))
batch = {item["title"]: item["status"] for item in items if item["title"].startswith("Batch ")}
expected = {"Batch One": "open", "Batch Two": "open"}
if batch != expected:
    raise SystemExit(f"batch statuses changed or missing: {batch!r}")
PY
}

setup_repo() {
    local name="$1"
    local repo="${WORK}/${name}"
    mkdir -p "$repo"
    git -C "$repo" init -q
    (
        cd "$repo"
        BD_NON_INTERACTIVE=1 run_bd init \
            --prefix q \
            --skip-agents \
            --skip-hooks \
            --setup-exclude \
            --role maintainer \
            --quiet >/dev/null 2>"${WORK}/${name}-init.err"
        run_bd config set status.custom \
            "backlog,pending-approval,ready,active,acceptance" >/dev/null
    )
    printf '%s\n' "$repo"
}

download_and_verify_candidate() {
    (
        cd "$WORK"
        curl -fsSLO "${RELEASE_BASE}/checksums.txt"
        curl -fsSLO "${RELEASE_BASE}/${TARBALL}"
        curl -fsSLO "${RELEASE_BASE}/${SPDX}"

        printf '%s  %s\n' "$EXPECTED_TARBALL_SHA" "$TARBALL" | sha256sum -c - >/dev/null
        grep "  ${TARBALL}\$" checksums.txt > "${TARBALL}.sha256"
        sha256sum -c "${TARBALL}.sha256" >/dev/null
        printf '%s  %s\n' "$EXPECTED_SPDX_SHA" "$SPDX" | sha256sum -c - >/dev/null

        tar -xzf "$TARBALL"
        printf '%s  bd\n' "$EXPECTED_BIN_SHA" | sha256sum -c - >/dev/null
    )
    BD="${WORK}/bd"
    export BD

    version_out="$(cd "$WORK" && run_bd version)"
    [ "$version_out" = "$EXPECTED_VERSION" ] \
        || fail "candidate version mismatch: ${version_out}"
    pass "downloaded official v${VERSION} candidate and verified fixed tarball, SPDX, binary hash, and version"
}

test_passthrough_streams_tty_and_signal() {
    repo="$(setup_repo passthrough)"
    signal_editor="${WORK}/signal-editor.sh"
    cat > "$signal_editor" <<'EOF'
#!/bin/sh
printf started > "$SIGNAL_STARTED"
trap 'exit 99' TERM
while :; do
    sleep 1
done
EOF
    chmod +x "$signal_editor"
    (
        cd "$repo"
        run_guard create --id q-pass --type task --title Pass --json >create.json
        run_bd version >direct-version.out 2>direct-version.err
        run_guard version >guard-version.out 2>guard-version.err
        diff -u direct-version.out guard-version.out >/dev/null

        printf 'create task 2 From stdin\n' \
            | run_guard batch --dry-run --json >guard-batch.out 2>guard-batch.err
        grep -qF "From stdin" guard-batch.out || fail "stdin batch passthrough lost stdin content"

        set +e
        run_bd does-not-exist >direct-missing.out 2>direct-missing.err
        direct_rc=$?
        run_guard does-not-exist >guard-missing.out 2>guard-missing.err
        guard_rc=$?
        set -e
        [ "$direct_rc" -eq "$guard_rc" ] || fail "unknown-command exit changed"
        [ "$guard_rc" -ne 0 ] || fail "unknown-command unexpectedly succeeded"
        diff -u direct-missing.out guard-missing.out >/dev/null
        diff -u direct-missing.err guard-missing.err >/dev/null \
            || fail "unknown-command stderr bytes changed"
        grep -qF "does-not-exist" guard-missing.err \
            || fail "unknown-command stderr was not preserved"

        tty_rc=0
        script -q -e -c "HOME='$HOME_T' XDG_CONFIG_HOME='$XDG_T' BEADS_ACTOR='E2E Test' LIVESPEC_BD_REAL='$BD' LIVESPEC_BD_GUARD_OTLP=on LIVESPEC_BD_GUARD_OTLP_ENDPOINT='http://127.0.0.1:1/v1/traces' '$WRAPPER' show q-pass" tty.out >/dev/null 2>tty.err || tty_rc=$?
        [ "$tty_rc" -eq 0 ] || fail "TTY passthrough command failed"
        grep -qF "q-pass" tty.out || fail "TTY passthrough lost candidate output"

        rm -f direct-signal-started guard-signal-started
        set +e
        setsid env \
            HOME="$HOME_T" \
            XDG_CONFIG_HOME="$XDG_T" \
            BEADS_ACTOR="E2E Test" \
            EDITOR="$signal_editor" \
            SIGNAL_STARTED="${PWD}/direct-signal-started" \
            "$BD" edit q-pass >direct-signal.out 2>direct-signal.err &
        direct_signal_pid=$!
        for _i in $(seq 1 50); do
            [ -s direct-signal-started ] && break
            sleep 0.1
        done
        [ -s direct-signal-started ] || fail "direct signal probe never reached blocking editor"
        kill -TERM -"${direct_signal_pid}" 2>/dev/null || kill -TERM "${direct_signal_pid}" 2>/dev/null || true
        wait "${direct_signal_pid}"
        direct_signal_rc=$?

        setsid env \
            HOME="$HOME_T" \
            XDG_CONFIG_HOME="$XDG_T" \
            BEADS_ACTOR="E2E Test" \
            EDITOR="$signal_editor" \
            SIGNAL_STARTED="${PWD}/guard-signal-started" \
            LIVESPEC_BD_REAL="$BD" \
            LIVESPEC_BD_GUARD_OTLP=on \
            LIVESPEC_BD_GUARD_OTLP_ENDPOINT="http://127.0.0.1:1/v1/traces" \
            "$WRAPPER" edit q-pass >guard-signal.out 2>guard-signal.err &
        guard_signal_pid=$!
        for _i in $(seq 1 50); do
            [ -s guard-signal-started ] && break
            sleep 0.1
        done
        [ -s guard-signal-started ] || fail "guard signal probe never reached blocking editor"
        kill -TERM -"${guard_signal_pid}" 2>/dev/null || kill -TERM "${guard_signal_pid}" 2>/dev/null || true
        wait "${guard_signal_pid}"
        guard_signal_rc=$?
        set -e
        [ "$direct_signal_rc" -eq "$guard_signal_rc" ] \
            || fail "signal exit changed: direct=${direct_signal_rc} guarded=${guard_signal_rc}"
        [ "$guard_signal_rc" -ne 0 ] \
            || fail "signal probe unexpectedly succeeded after SIGTERM"
        diff -u direct-signal.out guard-signal.out >/dev/null \
            || fail "signal probe stdout changed"
        diff -u direct-signal.err guard-signal.err >/dev/null \
            || fail "signal probe stderr changed"
    )
    pass "candidate passthrough preserves argv, JSON stdout, stdin, stderr, exit, TTY, and foreground signal behavior"
}

test_json_read_surfaces() {
    repo="$(setup_repo json-surfaces)"
    (
        cd "$repo"
        run_guard create --id q-parent --type task --title Parent --json >/dev/null
        run_guard create --id q-child --type task --title Child --json >/dev/null
        run_guard update q-child --parent q-parent --json >/dev/null
        run_guard comment q-parent "candidate comment" --json >comment-add.json

        run_guard list --status all --limit 0 --json >list.json
        run_guard show q-parent --json >show.json
        run_guard comments q-parent --json >comments.json
        run_guard children q-parent --json >children.json
        assert_json_array list.json
        assert_json_array show.json
        assert_json_array comments.json
        assert_json_array children.json
        python3 - list.json show.json comments.json children.json <<'PY'
import json
import sys

items = json.load(open(sys.argv[1], encoding="utf-8"))
shown = json.load(open(sys.argv[2], encoding="utf-8"))
comments = json.load(open(sys.argv[3], encoding="utf-8"))
children = json.load(open(sys.argv[4], encoding="utf-8"))
ids = {item["id"] for item in items}
assert {"q-parent", "q-child"} <= ids, ids
assert shown[0]["id"] == "q-parent", shown
assert comments[0]["issue_id"] == "q-parent", comments
assert "candidate comment" in comments[0]["text"], comments
assert children[0]["id"] == "q-child", children
assert children[0]["parent"] == "q-parent", children
PY
    )
    pass "candidate JSON list/show/comments/children surfaces parse through the guard"
}

test_lifecycle_controls() {
    repo="$(setup_repo lifecycle)"
    (
        cd "$repo"
        run_guard create --id q-life --type task --title Life --json >/dev/null

        run_guard update q-life --status active --json >active.json 2>active.err
        [ ! -s active.err ] || fail "lifecycle status emitted a warning"
        [ "$(field_of_object active.json status)" = "active" ] \
            || fail "lifecycle status did not apply"

        LIVESPEC_BD_GUARD_MODE=fail run_guard update q-life --status deferred \
            --json >status-deferred.json 2>status-deferred.err
        [ ! -s status-deferred.err ] || fail "modeled --status deferred emitted a warning"
        [ "$(field_of_object status-deferred.json status)" = "deferred" ] \
            || fail "candidate --status deferred did not apply"
        LIVESPEC_BD_GUARD_MODE=fail run_guard update q-life --status active \
            --json >/dev/null

        LIVESPEC_BD_GUARD_MODE=warn run_guard update q-life --status in_progress \
            --json >native.json 2>native.err
        grep -qF "bd update --status in_progress' is non-lifecycle" native.err \
            || fail "warn-mode native status did not warn"
        [ "$(field_of_object native.json status)" = "in_progress" ] \
            || fail "warn-mode native status did not pass through"

        LIVESPEC_BD_GUARD_MODE=fail run_guard update q-life --defer 2026-08-27 \
            --json >defer-flag.json 2>defer-flag.err
        [ ! -s defer-flag.err ] || fail "modeled update --defer emitted a guard warning"
        [ "$(field_of_object defer-flag.json status)" = "deferred" ] \
            || fail "candidate update --defer no longer writes status=deferred"

        LIVESPEC_BD_GUARD_MODE=fail run_guard update q-life --defer "" \
            --json >defer-clear.json 2>defer-clear.err
        [ ! -s defer-clear.err ] || fail "modeled update --defer clear emitted a guard warning"
        [ "$(field_of_object defer-clear.json status)" = "open" ] \
            || fail "candidate update --defer clear no longer writes status=open"
        LIVESPEC_BD_GUARD_MODE=fail run_guard update q-life --status active \
            --json >/dev/null

        set +e
        LIVESPEC_BD_GUARD_MODE=fail run_guard update q-life --claim \
            >claim.out 2>claim.err
        claim_rc=$?
        LIVESPEC_BD_GUARD_MODE=fail run_guard ready --claim \
            >ready.out 2>ready.err
        ready_rc=$?
        LIVESPEC_BD_GUARD_MODE=fail run_guard reopen q-life \
            >reopen.out 2>reopen.err
        reopen_rc=$?
        LIVESPEC_BD_GUARD_MODE=fail run_guard defer q-life \
            --json >defer-subcommand.json 2>defer-subcommand.err
        defer_rc=$?
        set -e
        if ! { [ "$claim_rc" -eq 3 ] && grep -qF "bd update --claim' is non-lifecycle" claim.err; }; then
            fail "fail-mode update --claim was not blocked"
        fi
        if ! { [ "$ready_rc" -eq 3 ] && grep -qF "bd ready --claim' is non-lifecycle" ready.err; }; then
            fail "fail-mode ready --claim was not blocked"
        fi
        if ! { [ "$reopen_rc" -eq 3 ] && grep -qF "bd reopen' is non-lifecycle" reopen.err; }; then
            fail "fail-mode reopen was not blocked"
        fi
        if ! { [ "$defer_rc" -eq 0 ] && [ ! -s defer-subcommand.err ]; }; then
            fail "fail-mode defer subcommand did not pass through as modeled"
        fi
        [ "$(field_of_object defer-subcommand.json status)" = "deferred" ] \
            || fail "candidate defer subcommand no longer writes status=deferred"

        set +e
        run_guard ready --status open --json >ready-filter.json 2>ready-filter.err
        ready_filter_rc=$?
        set -e
        [ "$ready_filter_rc" -ne 3 ] || fail "ready --status open list filter was guard-blocked"
        ! grep -qF "livespec bd-guard:" ready-filter.err \
            || fail "ready --status open list filter emitted guard warning"
    )
    pass "candidate-backed lifecycle writes pass, warn, fail, and preserve ready list filters"
}

test_create_normalization() {
    repo="$(setup_repo create-normalization)"
    selector_repo="$(setup_repo selector-target)"
    (
        cd "$repo"
        run_bd create --id q-unrelated --type task --title Unrelated --json >/dev/null

        run_guard create --id q-human --type task --title Human >human.out 2>human.err
        [ ! -s human.err ] || fail "human create emitted stderr"
        grep -qF "Created issue: q-human" human.out || fail "human create output shape changed"
        run_bd list --status all --limit 0 --json >after-human.json
        [ "$(status_of after-human.json q-human)" = "backlog" ] \
            || fail "human create was not normalized to backlog"
        [ "$(status_of after-human.json q-unrelated)" = "open" ] \
            || fail "human create normalized an unrelated native-open issue"

        run_guard create --id q-json --type task --title Json --json >create-json.out 2>create-json.err
        [ ! -s create-json.err ] || fail "qualifying JSON create emitted stderr"
        [ "$(field_of_object create-json.out status)" = "open" ] \
            || fail "candidate create output no longer reports native open"
        run_bd list --status all --limit 0 --json >after-json.json
        [ "$(status_of after-json.json q-json)" = "backlog" ] \
            || fail "JSON create was not normalized to backlog"
        [ "$(status_of after-json.json q-unrelated)" = "open" ] \
            || fail "JSON create normalized an unrelated native-open issue"

        run_guard create --id q-silent --type task --title Silent --silent >silent.out 2>silent.err
        [ ! -s silent.err ] || fail "explicit create --silent emitted stderr"
        silent_id="$(tr -d '[:space:]' < silent.out)"
        [ "$silent_id" = "q-silent" ] || fail "explicit create --silent did not output only the new id"
        run_bd list --status all --limit 0 --json >after-silent.json
        [ "$(status_of after-silent.json "$silent_id")" = "backlog" ] \
            || fail "explicit create --silent was not normalized to backlog"
        [ "$(status_of after-silent.json q-unrelated)" = "open" ] \
            || fail "explicit create --silent normalized an unrelated native-open issue"

        run_guard q "Quick item" >quick.out 2>quick.err
        [ ! -s quick.err ] || fail "quick-capture create emitted stderr"
        quick_id="$(tr -d '[:space:]' < quick.out)"
        run_bd list --status all --limit 0 --json >after-quick.json
        [ "$(status_of after-quick.json "$quick_id")" = "backlog" ] \
            || fail "quick-capture create was not normalized to backlog"
        [ "$(status_of after-quick.json q-unrelated)" = "open" ] \
            || fail "quick-capture create normalized an unrelated native-open issue"

        run_guard create --id q-event --type event --title Event --json >event.out 2>event.err
        [ ! -s event.err ] || fail "event create emitted stderr"
        run_bd list --status all --limit 0 --json >after-event.json
        [ "$(status_of after-event.json q-event)" = "open" ] \
            || fail "event create exclusion was normalized"

        run_guard create --id q-ephemeral --title Ephemeral --ephemeral --json >ephemeral.out 2>ephemeral.err
        run_bd list --status all --limit 0 --json >after-ephemeral.json
        if assert_no_issue after-ephemeral.json q-ephemeral
        then
            :
        else
            fail "ephemeral create created or normalized an issue"
        fi

        run_guard create --id q-dry --title Dry --dry-run --json >dry.out 2>dry.err
        run_bd list --status all --limit 0 --json >after-dry.json
        if assert_no_issue after-dry.json q-dry
        then
            :
        else
            fail "dry-run create created or normalized an issue"
        fi

        cat >batch-plan.md <<'EOF'
# Batch Plan

## Batch One

First batch body.

## Batch Two

Second batch body.
EOF
        run_guard create --file batch-plan.md >batch.out 2>batch.err
        [ ! -s batch.err ] || fail "batch create emitted stderr"
        grep -qF "Created 2 issues from batch-plan.md" batch.out \
            || fail "batch create did not report a successful two-issue create"
        run_bd list --status all --limit 0 --json >after-batch.json
        assert_batch_items_stayed_open after-batch.json \
            || fail "batch create was normalized by a flag-less follow-up or did not create both issues"

        run_guard create --id q-help --help >create-help.out 2>create-help.err
        [ ! -s create-help.err ] || fail "create help emitted stderr"
        if grep -Eq '(^|[[:space:]])(--status|-s)([=,[:space:]]|$)' create-help.out; then
            fail "candidate create help now advertises create-time status; redesign normalizer"
        fi

        set +e
        run_guard create --id q-future --status ready --title Future >future.out 2>future.err
        future_rc=$?
        set -e
        [ "$future_rc" -ne 0 ] || fail "candidate unexpectedly accepted create-time --status; redesign normalizer"
        [ ! -s future.out ] || fail "future-status rejection produced stdout that could be id-extracted"

        run_guard create -C "$selector_repo" --id q-selector --type task --title Selector --json >selector.out 2>selector.err
        [ ! -s selector.err ] || fail "selector create emitted stderr"
        run_bd list --status all --limit 0 --json >after-local-selector.json
        if assert_no_issue after-local-selector.json q-selector
        then
            :
        else
            fail "selector create appeared in the wrong repository"
        fi
        (cd "$selector_repo" && run_bd list --status all --limit 0 --json >"${WORK}/after-selector.json")
        [ "$(status_of "${WORK}/after-selector.json" q-selector)" = "open" ] \
            || fail "tenant selector exclusion was normalized by a flag-less follow-up"
    )
    pass "candidate create normalizes normal/silent/JSON ids and excludes selector, batch, event, ephemeral, dry-run, help, and future-status cases"
}

test_otlp_fail_open() {
    repo="$(setup_repo otlp)"
    (
        cd "$repo"
        # The emit is detached: the wrapper returns BEFORE its emit child
        # exits. A held stub emitter proves that by ordering, not by timing
        # the call, which measured host load rather than the detach contract.
        held="$(pwd)/held-emit"
        mkdir -p "$held"
        cat >"${held}/held-emit.py" <<'HELDPY'
import os
import pathlib
import time

held = pathlib.Path(os.environ["BDG_HELD_DIR"])
(held / "started").write_text("1")
for _ in range(1200):  # safety cap only (60 s); the test releases it first
    if (held / "release").exists():
        break
    time.sleep(0.05)
(held / "exited").write_text("1")
HELDPY
        BDG_HELD_DIR="$held" \
        LIVESPEC_BD_GUARD_EMIT="${held}/held-emit.py" \
        LIVESPEC_BD_GUARD_OTLP=on \
        LIVESPEC_BD_GUARD_OTLP_ENDPOINT="http://127.0.0.1:1/v1/traces" \
            run_guard_otlp list --status all --limit 0 --json >otlp-list.json 2>otlp-list.err
        [ ! -f "${held}/exited" ] || fail "OTLP emit child exited before the candidate wrapper returned"
        i=0
        while [ ! -f "${held}/started" ] && [ "$i" -lt 600 ]; do sleep 0.05; i=$((i + 1)); done
        [ -f "${held}/started" ] || fail "OTLP emit child never started for the candidate wrapper"
        : >"${held}/release"
        i=0
        while [ ! -f "${held}/exited" ] && [ "$i" -lt 600 ]; do sleep 0.05; i=$((i + 1)); done
        LIVESPEC_BD_GUARD_OTLP=on \
        LIVESPEC_BD_GUARD_OTLP_ENDPOINT="http://127.0.0.1:1/v1/traces" \
            run_guard_otlp list --status all --limit 0 --json >otlp-list.json 2>otlp-list.err
        [ ! -s otlp-list.err ] || fail "OTLP dead endpoint changed stderr"
        assert_json_array otlp-list.json

        set +e
        LIVESPEC_BD_GUARD_MODE=fail \
        LIVESPEC_BD_GUARD_OTLP=on \
        LIVESPEC_BD_GUARD_OTLP_ENDPOINT="http://127.0.0.1:1/v1/traces" \
            run_guard_otlp update q-none --claim >otlp-block.out 2>otlp-block.err
        block_rc=$?
        set -e
        [ "$block_rc" -eq 3 ] || fail "OTLP fail-mode block exit changed"
        grep -qF "bd update --claim' is non-lifecycle" otlp-block.err \
            || fail "OTLP fail-mode block warning missing"
    )
    pass "candidate guard warn/fail and OTLP dead-endpoint behavior are fail-open"
}

download_and_verify_candidate
test_passthrough_streams_tty_and_signal
test_json_read_surfaces
test_lifecycle_controls
test_create_normalization
test_otlp_fail_open

printf 'bd-guard candidate qualification passed in isolated temporary repositories\n'
