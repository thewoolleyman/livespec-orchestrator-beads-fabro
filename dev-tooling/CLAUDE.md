# dev-tooling/

Unlike the `livespec` repo, this plugin does NOT host its own Python
enforcement checks here — the shared (canonical) checks live in the
`livespec_dev_tooling` package (pinned in `pyproject.toml`) and are
invoked through the `just check-*` targets in the `justfile`. The
`checks/` subdir carries only this plugin's private, non-canonical
checks.

## Commit-refuse hook

The canonical STRUCTURAL commit-refuse hook body is NO LONGER vendored
here as a `.sh`. It ships in the `livespec_dev_tooling` wheel as the
SINGLE canonical-body carrier
(`livespec_dev_tooling.install_commit_refuse_hooks.CANONICAL_HOOK_BODY`),
so there is no per-repo copy to drift. `just install-commit-refuse-hooks`
— run by `just bootstrap`, by CI, and by the Fabro sandbox prepare step
— installs it via `uv run python -m
livespec_dev_tooling.install_commit_refuse_hooks` at ALL THREE hooks
(`.git/hooks/pre-commit`, `pre-push`, and `commit-msg`), resolving
`git rev-parse --git-common-dir` so the install lands in the primary's
shared hooks directory even when invoked from a worktree. The installed
body refuses commits/pushes STRUCTURALLY — it exits 1 when
`git rev-parse --git-dir` equals `git rev-parse --git-common-dir` (a
primary checkout; a secondary worktree's git-dir differs) UNLESS
`git config livespec.sandboxExempt` is `true` (the declared
Fabro-sandbox exemption) — so it is ARMED ON INSTALL with no
`livespec.primaryPath` arming step. It then delegates to lefthook at
worktrees (and in exempt sandboxes); the basename of `$0` selects which
hook's command list fires from `lefthook.yml`, and `"$@"` passes through
so the commit-msg message-file argv reaches the red-green-replay stage.
The dev-tooling check `primary_checkout_commit_refuse_hook_installed`
recognizes its fingerprint via substring match. To change the body,
edit the `livespec_dev_tooling` source upstream and bump the pin here —
never re-vendor a local copy.

## Rules for editing this tree

- `--no-auto-install` on every `lefthook run` invocation is
  load-bearing: omitting it lets lefthook auto-sync `.git/hooks/`
  against its own standard wrapper, clobbering the installed hook to
  `<name>.old` and silently disabling the gate. Never remove it.
- Do NOT weaken the refuse-at-primary branch: it lives in
  `livespec_dev_tooling.install_commit_refuse_hooks.CANONICAL_HOOK_BODY`
  upstream — its marker comment, the `git rev-parse --git-common-dir`
  comparison, and the `exit 1` branch together form the fingerprint the
  dev-tooling check matches.
- The task runner (`justfile`) is the single source of truth for
  dev-tooling invocations; hooks delegate via `lefthook` →
  `just <target>`, never by calling tools directly.
