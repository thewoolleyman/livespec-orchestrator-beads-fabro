#!/bin/sh
# codex-yolo-reapply — SessionStart hook.
#
# Forces the openai-codex plugin's Codex threads to danger-full-access ("YOLO":
# full disk + network, no OS sandbox), so plugin-driven Codex rescues AND reviews
# can actually execute (pytest / git / gh) instead of silently passing code they
# could never run.
#
# WHY self-carried: openai/codex-plugin-cc hardcodes a restrictive sandbox on
# every plugin-launched thread — buildThreadParams / buildResumeParams default to
# "read-only", and the review / adversarial-review / task sites pin
# read-only / workspace-write. None of those enable network. Upstream offers no
# toggle: every configurable-sandbox issue/PR is unmerged or author-withdrawn
# (see plan/codex-yolo-sandbox/research.md). A plugin refresh clobbers the cache,
# so this hook re-applies the patch every session. It is registered in
# .claude/settings.json under hooks.SessionStart AFTER `just ensure-plugins`
# (which may re-resolve and clobber the plugin), so ordering restores the patch.
#
# WHAT: rewrites the single sandbox chokepoint in every cached plugin version:
#
#     sandbox: options.sandbox ?? "read-only"
#         ->
#     sandbox: process.env.CODEX_COMPANION_SANDBOX || "danger-full-access"
#
# buildThreadParams / buildResumeParams are the ONLY two thread-param builders and
# every plugin path (task, review, adversarial-review, resume) flows through them,
# so this one line in codex.mjs covers all of them. The env var CODEX_COMPANION_SANDBOX
# is an escape-hatch: set it (e.g. to "read-only" or "workspace-write") to downgrade.
#
# Idempotent: rewrites only the stock read-only chokepoint; a no-op once patched.
# Fail-open: absent python3 or plugin cache -> pass through (exit 0). python3 is
# used only as an argv-based literal replacer, so the JS punctuation never has to
# survive sed/shell quoting.
if ! command -v python3 >/dev/null 2>&1; then
    exit 0
fi

STOCK='sandbox: options.sandbox ?? "read-only"'
PATCHED='sandbox: process.env.CODEX_COMPANION_SANDBOX || "danger-full-access"'

for f in "$HOME"/.claude/plugins/cache/openai-codex/codex/*/scripts/lib/codex.mjs; do
    [ -f "$f" ] || continue
    grep -qF "$STOCK" "$f" || continue
    python3 -c 'import sys; p=sys.argv[1]; s=open(p,encoding="utf-8").read(); open(p,"w",encoding="utf-8").write(s.replace(sys.argv[2],sys.argv[3]))' \
        "$f" "$STOCK" "$PATCHED" \
        && echo "[codex-yolo-reapply] forced danger-full-access in $f"
done

exit 0
