# Adopter dispatch setup

How to make factory dispatch work against **your own** repository, as an
adopter of this orchestrator plugin rather than a member of the livespec
fleet.

Installing the plugin does not provision a dispatch path. Three things
are yours to stand up, and only the first is any real work:

1. A **per-tenant Fabro server** holding your own GitHub App identity.
2. Nothing, for workflow selection — your repo's own
   `implement-work-item` workflow is resolved automatically.
3. Nothing, for the App `workflows` permission — that grant is withheld
   from the dispatch credential **by design**, and work needing it is
   routed elsewhere automatically.

The authority for all three is this repo's own spec:
`SPECIFICATION/contracts.md` §"Per-tenant engine identity" and §"The
dispatch credential set", and `SPECIFICATION/constraints.md` §"Factory
sandbox credential constraints". Where this document and those sections
disagree, the spec wins and this document is the defect.

## 1. Run your own Fabro server

**You cannot dispatch your repo through someone else's Fabro server.** A
server instance holds **exactly ONE** GitHub App integration — a
structural fact of the engine, not a configuration choice — so a server
carrying the fleet's App cannot reach your repository, because that App
is not installed on it. Adopter dispatch therefore runs against a
per-tenant server instance: your own process, your own App, your own
port.

Give it a dedicated `FABRO_HOME` (the directory the server reads
`settings.toml`, `storage/` and `environments/` from) so it shares
nothing with any other instance on the host. The fleet runs several
instances side by side on one machine this way.

### `settings.toml` — the non-secret settings

```toml
_version = 1

[server.integrations.github]
strategy = "app"
app_id = "<your own App's numeric id>"

[server.auth]
methods = ["dev-token"]

[server.listen]
address = "127.0.0.1:<your own port>"
type = "tcp"

[cli.target]
type = "http"
url = "http://127.0.0.1:<your own port>"

[server.api]
url = "http://127.0.0.1:<your own port>/api/v1"

[server.web]
enabled = true
url = "http://127.0.0.1:<your own port>"
```

`app_id` is **your own** App's id, and it is the only App field that
belongs in this file — `settings.toml` carries the App's identity and
**never key material**.

Bind to loopback on a host install and reach it over a private network
overlay rather than publishing it. (The containerized orchestrator binds
`0.0.0.0` instead, because a published container port has to be
reachable from outside the container; its host-side port still stays
loopback-bound.)

### The App private key — environment only

Export your App's PEM into the **server process environment** as
`GITHUB_APP_PRIVATE_KEY`:

```bash
GITHUB_APP_PRIVATE_KEY="$(cat /path/to/your-app.private-key.pem)"
```

Environment only — never in argv, and **never a settings key**. Fabro
then mints and refreshes its own installation tokens for its git legs
from that key.

Do **not** reach for `fabro install` to set this up. Its GitHub step
validates a static token and rejects App installation tokens (`ghs_*`)
by design, while the App strategy above is natively supported. Write the
settings and the server credentials directly, as
`orchestrator-image/orchestrator-entrypoint.sh` (`provision_fabro`)
does — that function is the executable form of this whole section.

### Dev-token auth

`methods = ["dev-token"]` requires **both** values below in the server's
environment at start, and the server **does not generate** either of
them for you. Put them in a mode-`600` `storage/server.env` under your
`FABRO_HOME`:

```
FABRO_DEV_TOKEN=fabro_dev_<64 hex characters>
SESSION_SECRET=<64 hex characters>
```

The dev token has a fixed format: the literal prefix `fabro_dev_`
followed by **64 lowercase hex** characters (74 bytes total). Any other
value is refused as an invalid format. Generate both with, for example,
`head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'`.

These are three separate start-up refusals, and each one is silent about
the next: a missing `SESSION_SECRET`, a missing `FABRO_DEV_TOKEN`, and a
dev token whose format is wrong. Expect to fix them one at a time.

Point the client at the server once per host:

```bash
fabro auth login --server http://127.0.0.1:<your own port> --dev-token <the dev token>
```

That writes `~/.fabro/auth.json`, keyed by the server url. A
`FABRO_DEV_TOKEN__<factory-name>` environment variable overrides it for
one named factory when you need something more specific than a login
file shared by every client on the host.

### The sandbox environment file

Copy `environments/livespec-ci.toml` into your `FABRO_HOME`'s
`environments/` directory. It is needed because the workflow's run
environment names it:

```toml
[run.environment]
id = "livespec-ci"
```

A server home without that environment cannot run the graph. The file
declares the sandbox provider, image and resources; copy the fleet's
verbatim to start, then edit the image to one that can build your
toolchain.

### Register it as a factory

Declare the server under `dispatcher.factories` in your repo's
`.livespec.jsonc` and select it with `dispatcher.default_factory`:

```jsonc
"dispatcher": {
  "default_factory": "mine",
  "factories": {
    "mine": { "server": "http://127.0.0.1:<your own port>" }
  }
}
```

`LIVESPEC_FABRO_FACTORY=<name>` overrides the choice for one invocation,
and `dispatcher.py dispatch` takes `--factory <name>`.

### Credentials the dispatch itself needs

Separately from the server, each dispatch needs its target's configured
`credential_wrapper` to inject the **full** credential set: the GitHub
App environment (`GITHUB_APP_ID` + `GITHUB_PRIVATE_KEY`, optionally
`GITHUB_APP_INSTALLATION_ID`), your work-items store secret, and the
engine LLM credential. Resolution is fail-closed — absent the App
environment and a wrapper to re-exec through, a dispatch refuses with a
diagnostic naming the missing variable rather than falling back to any
other credential. There is no fleet credential to inherit, and that is
the point: the fleet is adopter #0 and injects its own App through its
own wrapper exactly as you do.

## 2. Your `implement-work-item` workflow is resolved automatically

Commit your own workflow at

```
.fabro/workflows/implement-work-item/workflow.toml
```

in your repository, and it is **resolved automatically** on every
dispatch. There is **no `--workflow` flag** to hand-carry, and no
`--workflow-name` either: `implement-work-item` is a reserved name that
every dispatch target defines whether it registers anything else or not.

The resolution precedence, highest first:

| | Source |
|---|---|
| 1 | An explicit `--workflow <path>` — a raw-path **escape hatch** |
| 2 | A `dispatcher.workflows` registry entry's directory, when a dispatch selects that variant by name |
| 3 | **Your repo's own `.fabro/workflows/implement-work-item/workflow.toml`, when it exists** |
| 4 | The plugin's bundled workflow, for a target that commits none |

So `--workflow` exists for one-off raw-path overrides, not for ordinary
adopter dispatch. If you find yourself passing it on every dispatch, the
file is not where step 3 looks.

This matters beyond saving a flag, because the workflow config carries
the **sandbox image pin**. A repo whose toolchain differs from this
orchestrator's own — a Rust repo needing a Rust-capable image, against a
Python-only pin — governs its own execution substrate rather than
silently inheriting one that cannot build it. The same file is where
your prepare steps declare your toolchain's own facts; no fleet
toolchain constant is assumed for your target.

## 3. The App `workflows` grant is withheld by design

Do **not** grant `workflows` read-write to the App whose credential
reaches the factory sandbox. It is **withheld by design** — rejected,
**not deferred** — and it is not a gap for you to close.

The reason is that every gate in the factory's safety model is *defined
in* the files that grant makes writable. With it, an agent could
rewrite the implement → janitor → CI → merge chain and
**disable its own examiner** in the same pull request. The grant is also
**all-or-nothing**: GitHub offers no per-path or comment-only scoping,
so there is no narrower version to ask for.

Do not infer the posture from any other credential you hold. The
fleet's **fan-out credential** legitimately *does* hold `workflows`
read-write, because the fan-out is a narrow, deterministic pin-string
rewrite. The factory sandbox is an agent with open-ended latitude. The
asymmetry is correct, and neither credential's posture may be read off
the other's.

### Where the work goes instead

The resolution is **ROUTING, not privilege** — and it is
**never manual work**. Work whose scope requires the withheld capability
is routed to the **attended host session**, which already holds that
capability legitimately and where every diff is reviewed. Requiring you
to hand-edit a file is not an acceptable resolution and is not offered
as one; the boundary relocates *which actor publishes*, and it must not
cost autonomy.

The refusal is pre-dispatch, precise, and non-interactive: an item that
declares an edit under `.github/workflows/` is refused **before** a
sandbox launches, so no agent authors work that cannot be published, and
the refusal names the host-session route. The predicate keys on the
`.github/workflows/` path prefix specifically — composite actions under
`.github/actions/` stay publishable by the sandbox, so a broader
approximation would refuse dispatchable work.

Two things follow for how you write work-items:

- If an item only *mentions* a workflow path without shipping a change
  to one, record the citation-only override —
  `set-workflow-scope-override:<id>:citation-only` — or state inline
  that the item ships no files under `.github/workflows/`.
- If an item's scope only *partly* needs the capability, split it, so
  the portion the sandbox can publish is not refused along with the
  portion it cannot.

## See also

- `SPECIFICATION/contracts.md` §"Per-tenant engine identity", §"The
  dispatch credential set", §"Self-contained plugin dispatch".
- `SPECIFICATION/constraints.md` §"Factory sandbox credential
  constraints".
- `SPECIFICATION/scenarios.md` §"Scenario 32 — Adopter-target dispatch
  compatibility", which this document is the adopter-facing half of.
- `orchestrator-image/README.md` for the fleet's own server instances,
  their units and their verification commands — a worked example of
  several per-tenant servers on one host.
