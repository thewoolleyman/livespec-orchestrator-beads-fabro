# dev-tooling/

Standalone git-hook shell scripts installed by `just bootstrap` into
`.git/hooks/`. Unlike the `livespec` repo, this plugin does NOT host
its own Python enforcement checks here — the shared checks live in
the vendored `livespec_dev_tooling` package and are invoked through
the `mise exec -- just check-*` targets in the `justfile`.

- `git-hook-wrapper.sh` — the lefthook dispatcher installed at
  `.git/hooks/pre-commit` and `.git/hooks/pre-push`. It bypasses the
  PATH search that fails in non-mise-activated shells (e.g. Claude
  Code's default Bash) by invoking `mise exec lefthook -- lefthook
  run --no-auto-install "$HOOK_NAME"`. The basename of `$0` selects
  which hook's command list fires from `lefthook.yml`.
- `livespec-commit-refuse-hook.sh` — the canonical commit-refuse
  hook body per `livespec/SPECIFICATION/non-functional-requirements.md`
  §"Primary-checkout commit-refuse hook". It refuses commits/pushes
  when `git rev-parse --show-toplevel` equals `livespec.primaryPath`
  (the primary checkout), then delegates to lefthook at secondary
  worktrees. The doctor invariant
  `primary-checkout-commit-refuse-hook-installed` recognizes its
  fingerprint via substring match.

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
  `show-toplevel` comparison, and the `exit 1` branch together form
  the fingerprint the doctor invariant matches.
- The task runner (`justfile`) is the single source of truth for
  dev-tooling invocations; hooks delegate via `lefthook` →
  `just <target>`, never by calling tools directly.
