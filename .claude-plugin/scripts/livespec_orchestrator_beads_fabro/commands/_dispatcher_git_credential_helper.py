"""The sandbox git credential helper every Dispatcher-launched run configures.

WHY THE HELPER EXISTS (work-item bd-ib-52zt3o, Scenario 29). On the pinned
0.254 engine an in-sandbox `git push` never needed a credential helper: Fabro
wrote a token into the origin URL and re-minted it at each ACP node entry, and
git used the URL's own credential. The Petri-era standalone runner does
NEITHER. It says so at admission, in as many words — `run.integrations` is
ignored because "platform integrations are supplied by an embedding host, not
the standalone runner", and `run.git`, `run.run_branch`, `run.pull_request`,
`run.meta_branch` and `run.checkpoint` are ignored because "the standalone
runner performs no Git operations of its own". So on that engine every
in-sandbox push — the `needs_human` preserve push, `publish_draft`, `pr` —
arrives with no credential whatsoever. Measured on hp-candidate run
01M4NWARSD8T70G09PRQ70ZR5B: 30 prepare steps and a real `dod_gate` turn
succeeded, then `needs_human` printed LIVESPEC_NEEDS_HUMAN_PUSH_FAILED because
its `git push origin HEAD:refs/heads/needs-human/<run id>` had nothing to
authenticate with.

WHY A HELPER AND NOT A PROJECTED TOKEN. A token is a VALUE and would have to be
stored somewhere a push could read it — a git config file, a prepare step, the
immutable server-side workflow version. An installation token lives about an
hour while a run lives for several, so a stored one is both a durable copy of a
credential and, by the time the pr stage pushes, expired. A HELPER is a
COMMAND: git runs it at the moment of each push and the token exists only for
that exchange. The sandbox already carries one such command — the refreshing
`gh` wrapper `_dispatcher_gh_refresh` materializes, which mints a fresh App
installation token from the projected App inputs on every invocation — and
`gh auth git-credential` is gh's own credential-helper surface over it
(`gh auth setup-git` writes this exact configuration). Measured against gh
2.102.0 under that wrapper: it returns `username=x-access-token` plus a
freshly-minted installation token, and prints its "github-token source:" line
to stderr, which git ignores.

WHY THIS LEAVES THE PINNED ENGINE ALONE. git consults no credential helper for
a URL that already carries both a username and a password, so on the pinned
engine the token Fabro embedded in the origin URL is still what authenticates
and this configuration is inert. That is a property of git's own precedence
rather than of anything arranged here, which is why the two cases are asserted
as a pair.

WHY THE OVERLAY AND NOT `workflow.toml`, and why UNCONDITIONALLY. The committed
run config is FORKED per repository, so a prepare step written into one fork
covers one consumer and silently omits the rest — the same reason
`_dispatcher_factory_provenance` gives for injecting there. And the step is
rendered whether or not the App inputs are present: with them, `gh` on PATH is
the refreshing wrapper and the token is minted per push; without them the
wrapper is not installed and gh answers from the ambient `GITHUB_TOKEN` the
overlay's credential projection always carries. Rendering it inside the App
condition would cover the arm that happens to hold on this factory and leave
the other arm with no credential at all.
"""

from __future__ import annotations

import json
import shlex

__all__: list[str] = [
    "GITHUB_CREDENTIAL_HELPER_COMMAND",
    "GITHUB_CREDENTIAL_URL",
    "git_credential_helper_prepare_steps_block",
]

# The URL git scopes the helper to. It becomes the git-config SUBSECTION —
# everything between the first and the last dot of `credential.<url>.helper` —
# so it is a URL and not a hostname by design: git matches a request's
# protocol and host against it, and a bare `github.com` would match no https
# request at all.
GITHUB_CREDENTIAL_URL = "https://github.com"
# A git credential helper beginning with `!` is run as a shell command, with
# the operation (`get` / `store` / `erase`) appended as an argument. `gh` is
# resolved from PATH at that moment rather than by absolute path, which is what
# makes the wrapper's in-place replacement of the real binary take effect.
GITHUB_CREDENTIAL_HELPER_COMMAND = "!gh auth git-credential"


def git_credential_helper_prepare_steps_block() -> str:
    """Render the git-credential-helper `[[run.prepare.steps]]` block.

    LOCAL config, not `--global`: the clone the prepare chain runs in is the
    one every in-sandbox push pushes from, and the sibling `git config
    {{ inputs.sandbox_exempt_marker }} true` step already proves that scope
    reaches it. `--global` would additionally depend on `$HOME` being writable,
    and a prepare step that fails kills the run before any work is driven.

    The helper command is `shlex.quote`-ed because the step body is a shell
    command and the command carries spaces and a leading `!`; the whole script
    is then `json.dumps`-ed to TOML-quote it, matching every sibling block in
    the overlay.
    """
    key = f"credential.{GITHUB_CREDENTIAL_URL}.helper"
    script = f"git config {shlex.quote(key)} {shlex.quote(GITHUB_CREDENTIAL_HELPER_COMMAND)}"
    lines = [
        "",
        "# --- Dispatcher-materialized git credential helper: route every",
        "# --- in-sandbox push to github.com through the refreshing `gh` wrapper,",
        "# --- so the Petri-era runner's credential-free origin URL still",
        "# --- authenticates with a token minted at push time (bd-ib-52zt3o) ---",
        "[[run.prepare.steps]]",
        f"script = {json.dumps(script)}",
    ]
    return "\n".join(lines) + "\n"
