#!/bin/sh
# codex-yolo-reapply — SessionStart hook.
#
# Forces the openai-codex plugin's Codex threads to danger-full-access ("YOLO":
# full disk + network, no OS sandbox), so plugin-driven Codex rescues AND reviews
# can actually execute (pytest / git / gh) instead of silently passing code they
# could never run. Registered in `.claude/settings.json` under `hooks.SessionStart`
# AFTER `just ensure-plugins` (which may re-resolve and clobber the plugin cache),
# so the ordering restores the patch every session.
#
# Fail-open: if `python3` is absent, pass through (exit 0). All classification,
# rewrite, and drift-canary logic lives in the paired `codex_yolo_reapply.py`,
# kept importable so it is unit-testable without spawning this script
# (`check-tests-no-subprocess-spawn`). Same idiom as `beads-access-guard.sh`.
if ! command -v python3 >/dev/null 2>&1; then
    exit 0
fi
exec python3 "$(dirname "$0")/codex_yolo_reapply.py"
