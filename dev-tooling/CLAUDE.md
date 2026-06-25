# dev-tooling/

Standalone git-hook shell scripts installed by `just bootstrap` into
`.git/hooks/`. Unlike the `livespec` repo, this plugin does NOT host
its own Python enforcement checks here — the shared checks live in
the vendored `livespec_dev_tooling` package and are invoked through
the `mise exec -- just check-*` targets in the `justfile`.

- `livespec-commit-refuse-hook.sh` — the canonical STRUCTURAL
  commit-refuse hook body (byte-identical to livespec-dev-tooling
  v0.18.0) per `livespec/SPECIFICATION/non-functional-requirements.md`
  §"Primary-checkout commit-refuse hook". `just bootstrap` installs
  it at ALL THREE hooks (`.git/hooks/pre-commit`, `pre-push`, and
  `commit-msg`). It refuses commits/pushes STRUCTURALLY — it exits 1
  when `git rev-parse --git-dir` equals `git rev-parse
  --git-common-dir` (a primary checkout; a secondary worktree's
  git-dir differs) UNLESS `git config livespec.sandboxExempt` is
  `true` (the declared Fabro-sandbox exemption) — so it is ARMED ON
  INSTALL with no `livespec.primaryPath` arming step. It then
  delegates to lefthook at worktrees (and in exempt sandboxes); the
  basename of `$0` selects which hook's command list fires from
  `lefthook.yml`, and `"$@"` passes through so the commit-msg
  message-file argv reaches the red-green-replay stage. The
  dev-tooling check `primary_checkout_commit_refuse_hook_installed`
  recognizes its fingerprint via substring match.
- `git-hook-wrapper.sh` — the legacy lefthook-only dispatcher (no
  refuse branch). RETAINED as the family-template artifact and the
  `.fabro` sandbox-prepare fallback candidate, but NO LONGER
  installed by `install-commit-refuse-hooks` — the structural body
  above now serves commit-msg too, so all three hooks carry the
  refuse guard.

Rules an agent editing this tree must follow:

- `--no-auto-install` on every `lefthook run` invocation is
  load-bearing: omitting it lets lefthook auto-sync `.git/hooks/`
  against its own standard wrapper, clobbering these custom scripts
  to `<name>.old` and silently disabling the gate. Never remove it.
- Keep these portable `#!/bin/sh` scripts; do NOT add bashisms or
  hard-code interpreter paths other than the mise/git invocations
  shown.
- Do NOT weaken the refuse-at-primary branch in
  `livespec-commit-refuse-hook.sh` — its marker comment, the
  `git rev-parse --git-common-dir` comparison, and the `exit 1`
  branch together form the fingerprint the dev-tooling check
  matches.
- The task runner (`justfile`) is the single source of truth for
  dev-tooling invocations; hooks delegate via `lefthook` →
  `just <target>`, never by calling tools directly.
