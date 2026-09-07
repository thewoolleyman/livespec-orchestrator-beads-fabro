# Agent instructions

This file is the canonical agent-orientation surface for this repo;
`.claude/CLAUDE.md` is a symlink to it — never maintain a separate copy.
The sections through "Red-Green-Replay commit protocol" are the livespec
family-universal agent-instruction core (shared by every family member via
the impl-plugin template); repo-specific guidance is additive on top.

## Repository mutation protocol

Every repo change uses a worktree → PR → merge → cleanup path. Treat leaving
dirty state, committing on the primary checkout, or asking the user whether to
commit as failures of the workflow, not as acceptable stopping points.

1. Confirm the primary checkout before editing:

   ```bash
   git config --get livespec.primaryPath
   git status --short --branch
   ```

2. If the change will modify tracked files, create a dedicated worktree from the
   primary checkout's `master` and do all edits there. Every worktree lives under
   the per-user root `~/.worktrees/<repo>/<branch>` — NEVER as a peer of the
   clones under `/data/projects`, so the workspace holds only first-class clones.
   Create it with the worktree-discipline pack's recipe, which adds the
   worktree under that root, provisions the gitignored pack into it, and
   runs the hydrate hook (run it from the primary checkout):

   ```bash
   mise exec -- just worktree-create <branch>
   ```

   A raw `mise exec -- git -C /data/projects/livespec-orchestrator-beads-fabro worktree add -b <branch>
   "$HOME/.worktrees/livespec-orchestrator-beads-fabro/<branch>" master` also yields a usable
   worktree — the pre-commit and pre-push hooks install the pack before
   any gate reads it, so the worktree can commit and push with no
   `just bootstrap` — but it skips hydration, so prefer the recipe.

   `just bootstrap` registers `~/.worktrees` as one of mise's
   `trusted_config_paths`, so a freshly created worktree's `.mise.toml` is
   auto-trusted and the first `mise exec` inside it never stalls on a "config not
   trusted" prompt.

3. Use `mise exec -- git commit ...` and `mise exec -- git push ...` so the
   mise-managed lefthook hooks actually run. Never pass `--no-verify`; if a hook
   fails, fix the cause or halt with the failure.
4. Open a PR, wait for required checks, and merge through the PR using the repo's
   rebase-merge discipline.
5. After merge, refresh the primary checkout to `origin/master`, remove the
   feature worktree, delete the local branch, and verify the primary checkout is
   clean on `master`.

Do not leave orphaned worktrees. If a session must stop before cleanup, record
the active worktree path, branch, PR, validation state, and next action in the
relevant handoff document.

## Agent prerequisites for plugin work

When investigating or changing anything related to the Claude Code plugin
installation, marketplace, or distribution, establish execution context FIRST —
do not assume how the system works:

1. Run `claude plugin marketplace list` to see which marketplaces are configured
   and whether they point to local files or remote repos. Changes to a local
   `marketplace.json` do NOT affect installs from a remote GitHub marketplace.
2. Trace where the actual install command fetches from (local vs remote) before
   changing anything, and verify your change affects that code path.
3. For remote marketplaces, push to GitHub then test; for local, use
   `/plugin marketplace add ./.claude-plugin/marketplace.json`. Never test local
   changes against a remote marketplace and assume they apply.

## Codex dogfooding (OpenAI Codex CLI/TUI)

This repo's `/livespec:*` and orchestrator surfaces can ALSO be dogfooded from
OpenAI Codex CLI/TUI, not just Claude Code. Unlike the Claude path (plugins
enabled PER PROJECT via a committed `.claude/settings.json`), Codex plugin
enablement is **HOST-WIDE**: each registration persists in `~/.codex/config.toml`
and applies to every project on the host. Codex offers no project-scoped plugin
enablement, so there is no committed-settings analogue for the Codex path.

Install the three plugins host-wide — livespec CORE (the artifact carrier that
ships the spec-side prose and wrappers), the `livespec-driver-codex` Codex Driver
(which supplies the `/livespec:*` operation surface over core's prose), and THIS
repo's own orchestrator plugin (whose name is declared in this repo's
`.claude-plugin/plugin.json` — e.g. `livespec-orchestrator-beads-fabro`,
`livespec-orchestrator-git-jsonl`; substitute it for `<orchestrator-plugin>`
below):

```bash
# livespec CORE (spec-side prose + wrappers; no skills of its own):
codex plugin marketplace add thewoolleyman/livespec
codex plugin add livespec@livespec

# The Codex Driver (supplies the spec-side /livespec:* operation surface):
codex plugin marketplace add thewoolleyman/livespec-driver-codex
codex plugin add livespec@livespec-driver-codex

# This repo's orchestrator plugin (ships its OWN cross-runtime Codex surface):
codex plugin marketplace add thewoolleyman/<orchestrator-plugin>
codex plugin add <orchestrator-plugin>@<orchestrator-plugin>
```

Once installed, Codex operations are driven via `codex exec` and NAME-selected as
`<plugin>:<op>` (e.g. `livespec:next`, `<orchestrator-plugin>:list-work-items`)
rather than as `/`-prefixed slash commands. The distributed Drivers resolve their
prose at runtime — no `AGENTS.md` skill→prose mapping is required. See
`livespec/SPECIFICATION/contracts.md` §"Plugin distribution" and
`livespec/SPECIFICATION/non-functional-requirements.md` §"Codex dogfooding
contracts" for the authoritative install and resolution contracts; each
orchestrator plugin's repository owns its own Codex Driver mapping. A temporary
local Codex marketplace registration used for testing MUST be removed afterward
unless you explicitly ask to keep it.

The Codex TUI picker displays skills by short name with the plugin as context.
In `/skills` → `List skills` (or the `@` picker), search `drive`; the
row renders as `drive (livespec-orchestrator-beads-fabro)` with kind
`Skill`. The colon-qualified form
`livespec-orchestrator-beads-fabro:drive` is still valid for prompt /
`codex exec` name selection and model-visible skill references, but it is not
the picker row operators should expect.

**A RAW `codex exec` invocation MUST redirect stdin from a source that reaches
EOF** — normally `< /dev/null` when the prompt is passed as an argument (or a
heredoc / file when using stdin-prompt mode). Never leave stdin inherited.
`codex exec` reads *additional* prompt text from stdin until EOF even when a
prompt argument is present (it prints `Reading additional input from stdin...`);
a background/detached or subagent-spawned call inherits an open **socket** that
never closes, so codex blocks on that read forever, before doing any work —
the process stays alive (a status check reports "running") while its output
never grows past that one line. A foreground call works only because it inherits
`/dev/null`. This trap hits ONLY raw `codex exec`; the plugin's own
`codex-companion.mjs` runtime spawns with `stdio: "ignore"` and is immune, so
prefer routing through the companion / `codex:codex-rescue`. When you must call
`codex exec` directly, use the redirect form, e.g.
`codex exec -s read-only -m gpt-5.5 "$(cat prompt.txt)" < /dev/null > out.log 2>&1`.
And NEVER treat "the process is alive" as proof of progress — verify the output
file is growing past the stdin line.

**The codex-companion runtime is patched to always run `danger-full-access`
(YOLO): full disk + network, no OS sandbox.** Upstream `openai/codex-plugin-cc`
hardcodes a restrictive sandbox on every plugin-launched thread (`read-only` /
`workspace-write`, both network-OFF), which silently cripples Codex reviews — an
adversarial review that cannot run `pytest`/`gh` passes code it never executed.
Upstream ships no toggle and has merged no fix (prior-art survey:
`plan/codex-yolo-sandbox/research.md`), so this repo self-carries a one-line
chokepoint rewrite in the plugin cache — `buildThreadParams` / `buildResumeParams`
in `lib/codex.mjs` resolve to `danger-full-access` — re-applied every session by
the distributed orchestrator plugin hook in `.claude-plugin/hooks/hooks.json`
(because a plugin refresh clobbers the cache).
To DOWNGRADE a single run, set `CODEX_COMPANION_SANDBOX` (e.g. `read-only` or
`workspace-write`) in the environment — that env var is the escape-hatch the
chokepoint honors. `~/.codex/config.toml` also carries
`sandbox_mode = "danger-full-access"` to cover the raw `codex exec` path.
Rationale, end-to-end proof, and the deferred fork / host-wide options are in
`plan/codex-yolo-sandbox/handoff.md`.

## pi dogfooding (`@earendil-works/pi-coding-agent`)

This repo's operation surface can also be dogfooded from the pi coding agent,
alongside Claude Code and OpenAI Codex. Unlike Codex's host-wide plugin
registration, pi package enablement is project-scoped: the package install
creates project-local state under `.pi/`, and pi's project-trust gate controls
whether that state is honored.

Install the three pi git packages in the governed project: livespec CORE, the
`livespec-driver-pi` pi Driver, and THIS repo's orchestrator package:

```bash
# livespec CORE (spec-side prose + wrappers):
pi install git:github.com/thewoolleyman/livespec@release -l --approve

# The pi Driver (supplies the spec-side livespec-* pi skill surface):
pi install git:github.com/thewoolleyman/livespec-driver-pi@release -l --approve

# This repo's orchestrator package (ships its OWN pi skill bindings):
pi install git:github.com/thewoolleyman/livespec-orchestrator-beads-fabro@release -l --approve
```

pi has a flat skill namespace: it cannot express the Claude/Codex
`/livespec-orchestrator-beads-fabro:<op>` form. This package therefore exposes
each operation as `livespec-orchestrator-beads-fabro-<op>`; for example,
`drive` is registered as `livespec-orchestrator-beads-fabro-drive`. Keep the
full prefix. Shortening it is forbidden because other fleet repos share the
same suffix.

Each pi binding lives under `.claude-plugin/.pi-plugin/skills/`, and the
binding directory name MUST equal the frontmatter `name`. pi has tolerated a
directory/frontmatter mismatch, but the Agent Skills standard does not, and
this repo's `check-pi-plugin-structure` gate rejects the mismatch. Frontmatter
values that contain `: `, such as descriptions with `Mutating: ...`, must be
quoted so pi parses the field instead of silently dropping it.

Do not claim pi support from a non-interactive one-shot alone. A
non-interactive pi invocation (`-p`, `--mode json`, `--mode rpc`) can silently
ignore project-local packages unless trust is already established. Claim or
debug pi support only after a live interactive pi session shows this package's
skills in pi's human discoverability surface and drives an operation through the
installed package. Use a scoped tmux socket for scripted evidence; never use the
default tmux socket for repo acceptance proof.

## Beads runtime prerequisites

This plugin's work-item store is a per-repo beads/Dolt TENANT on the shared
family dolt-server — NOT JSONL files. Installing the plugin does NOT provision
the backend; a clone connects to its tenant only when ALL of the following are
present:

- **`bd` CLI, pinned**, through the public lifecycle-guard entry point at
  `/usr/local/bin/bd`. This repo's mise config MUST NOT declare or install
  `bd`: an activated mise tool or regenerated shim can shadow that policy
  boundary. When `LIVESPEC_BD_PATH` is set it MUST point at
  `/usr/local/bin/bd`; otherwise `bd` on `PATH` MUST resolve there. Normal
  plugin, ledger, and operator calls MUST NOT invoke the guard's private
  delegate executable.
- **A running Dolt `sql-server`** reachable over **TCP `127.0.0.1:3307`**. Family
  tenants force TCP (not the unix socket); `.beads/config.yaml` carries `dolt.*`
  host/port keys with NO `socket` key.
- **The tenant password** in env as a single **bare `BEADS_DOLT_PASSWORD`** —
  injected by THIS project's configured env wrapper. A FAMILY tenant shares the
  one family password via the family 1Password Environment wrapper
  `with-livespec-env.sh` (canonical copy at
  `/data/projects/1password-env-wrapper/with-livespec-env.sh`); an INDEPENDENT
  (non-family) tenant injects its own tenant password from its own 1Password
  Environment via its own `with-<project>-env.sh` wrapper. Either way `bd`
  consumes the same bare var — there is NO per-tenant
  `BEADS_DOLT_PASSWORD_<tenant>` variable and NO per-tenant→bare mapping. Real
  isolation comes from the per-tenant SQL user + DB-scoped grant, not from
  password distinctness or wrapper identity. Secrets are probe-only — `printenv
  NAME | wc -c`, never echo values — and NEVER committed to `.livespec.jsonc` or
  `.beads/`.
- **The `.beads/` pointer files**: `config.yaml` (committed; the `dolt.*` server
  keys) and `metadata.json` (gitignored, regenerable). NEVER run `bd init` inside
  a primary checkout or worktree — it auto-commits and clobbers `.beads/`.

**NEVER install beads v1.2.0 or v1.2.1 — a single invocation strands every
tenant on the shared server.** Upstream published both **by accident on
2026-08-11 without release testing**. Running the v1.2.1 binary **even once**
migrates the database schema from **v53 to v65**, after which every v1.1.2 /
v1.2.2 binary refuses with `schema version mismatch: database is at v65, binary
knows up to v53`. Upstream's recovery guidance assumes a local single-clone
database; **we run a shared multi-tenant Dolt server**, so one invocation
against a shared tenant strands that tenant for every client in the family —
currently **14 live tenants**. v1.2.1 is marked prerelease rather than
withdrawn, so it is **still downloadable**: this is a live hazard, not history.
The current stable is **v1.2.2**, which is a recovery release re-issuing the
tested 1.1 line. **This host's `/usr/local/bin/bd-real` was cut over to v1.2.2
on 2026-08-31 and every family tenant is at schema v53** (receipt:
`plan/beads-v1-1-2-upgrade/research/cutover-receipt-2026-08-31.md`). Two facts
from that cutover that bite any future upgrade: `bd migrate --dry-run` is NOT a
preview — a v1.2.x binary migrates an older store ON OPEN, before printing
"Version matches" — so probe an un-migrated tenant only through mysql, never
through any `bd` verb; and a fleet pause must stop the ROOT system timer
`reconcile-runs.timer` (`systemctl list-timers --all`, system AND user manager),
which reads this repo's ledger every ten minutes and auto-migrated this tenant
mid-cutover. That attribution came from the SUDO JOURNAL, which is the
instrument for "which process touched a tenant": every `with-*-env.sh` wrapper
call re-execs through `sudo`, so `journalctl --since <t1> --until <t2>
-o short-iso _COMM=sudo | grep 'PWD=/data/projects/<repo>'` lists each call
with its full command, and `-o verbose` adds the owning `_SYSTEMD_UNIT`; the
Dolt server's own journal logs nothing per connection. If a database has already been migrated to v65, do NOT
improvise: roll the schema cursor back per upstream's `docs/RECOVERY-1.2.1.md`
(at tag v1.2.2), use `BD_IGNORE_SCHEMA_SKEW=1` only as a stopgap, and upgrade
**every** clone before recovering — a leftover v1.2.1 binary silently
re-migrates. Measured 2026-08-20: nothing in this repo or the eleven sibling
repos resolves a beads version dynamically, so the exposure is human, not
mechanical. Full evidence:
`plan/beads-v1-1-2-upgrade/research/release-target-restatement-2026-08-20.md`;
ledger item `bd-ib-3kolea.4`.

**Run beads commands from the target repo root.** Per-command `bd` resolves its
connection from the current directory's `.beads/config.yaml` (auto-discovery),
NOT from any resolved config object — so run from the intended repo's root, or
`bd` silently operates on the wrong tenant.

**An "Access denied" / "no beads database found" failure almost always means you
are running OUTSIDE the wrapper** (the bare `BEADS_DOLT_PASSWORD` is absent), not
that a secret is missing. Re-run under your project's configured env wrapper
(`with-<project>-env.sh`) -- `<command>`. Never hand-hunt the secret or reach
around the seam with raw `mysql` / `dolt` / `sudo`.

**`bd list --status open` matches NOTHING here.** This store holds livespec
lifecycle statuses — `backlog`, `ready`, `blocked`, `active`, `acceptance`,
`pending-approval`, `closed`. The beads-native `open` / `in_progress` names are
normalized away (`_NATIVE_STATUS_REMAP` in
`commands/_dispatcher_ledger_close.py` maps `open`→`backlog`,
`in_progress`→`active`), so a native-name filter silently returns an empty set
rather than erroring. To survey the ledger, list everything and filter
client-side: `bd list --status all --limit 0 --json`.

**`bd ready` is DEAD here for the same reason — it returns an empty set while
ready work exists.** It filters on the beads-native `open` status this store
never uses, so it reports `✨ No open issues` and exits 0. Measured 2026-08-19
on this tenant: `bd ready --json` returned `[]` while **18** items sat at
`status == ready`, including one with an empty dependency list. `--limit 0`
changes nothing; this is the status filter, not the row cap and not blocker
filtering. Do not use it to choose work. **Use this plugin's `next` operation.**

**Do NOT substitute a `status == ready` filter for `next`: `ready` is a
lifecycle status, not a computed readiness, and filtering on it IGNORES
BLOCKERS.** An item sits at `status == ready` while a dependency of it is still
open, so a filter picks work that must not start yet — and picks it silently,
because the row looks exactly like genuinely-ready work. Measured 2026-08-20 on
the `openbrain` tenant: `bd list --status all --limit 0 --json` filtered on
`status == ready` returned `ob-uhiint`, whose `dependency_count` is 1 and whose
blocker `ob-zmrbcy` was `active` at the time — and whose own notes say it must
be written only after that sibling lands. The plugin's `next` returned
`candidates: []` for the same tenant in the same minute. `next` is right and
the filter is wrong; that is the whole reason the ranking lives in the
operation rather than in a one-liner.

Use the filter ONLY to survey what exists, never to choose what to start.

**Status-conformance refusal trap signature.** A pre-dispatch ledger
conformance refusal presents as `drive.py` exit 1 + dispatcher exit 1 + no
phantom claim. That discriminates it from the anchor-as-dependency trap, which
uses dispatcher exit 3. Ask which surface produced the conformance finding
before concluding dispatch is blocked: dispatch/gate surfaces auto-heal
beads-native `open` / `in_progress`, while raw check surfaces report them as
status findings; beads-native `deferred` is modeled as a parked, conforming
status and must not block unrelated items tenant-wide.

**`--status all` is load-bearing: without it `bd list` HIDES EVERY CLOSED
ITEM.** A bare `bd list --limit 0 --json` returns only non-closed work, and it
reports that truncated set as a normal, plausible, non-empty result — there is
no warning and no error. Measured 2026-08-19: on this repo's tenant the bare
form returned 173 items against 588 with `--status all`, hiding a 415-item
closed set; on the `dolt-server` tenant it returned 4 against 72, i.e. **6% of
the ledger**. `BeadsClient.list_issues` already emits the `--status all` form,
so code and operators otherwise survey different ledgers.

**Enumerating an epic's children: NEITHER the id-prefix form NOR the `parent`
field is complete on its own.** The store links children two ways, and each
hand-rolled filter is blind to one of them. An explicit `parent-child`
dependency edge populates `parent` in `bd list --json`; the implicit dotted-id
hierarchy does NOT — `bd` honours it (it refuses to add a redundant edge,
saying "already a child of `<epic>` … would create a deadlock") while the JSON
listing still reports `parent: null`. Measured 2026-08-19 on `bd-ib-l3nptz`:
filtering on `parent == "bd-ib-l3nptz"` returned **22** children and silently
omitted `bd-ib-l3nptz.16`, which exists and is `backlog`; the prefix form has
the mirror-image blind spot, catching `.16` but missing **seven** children
whose ids are not dotted. Both forms return a plausible non-empty set, so
neither announces the omission. Use the package primitive —
`undisposed_plan_child_ids` / `client.children()`, which unions both linkage
mechanisms — and never a `bd list --json` filter of either shape. (The plan
archive gate already uses the union and is therefore correct; the exposure is
to humans and agents surveying by hand.)

**`bd show --json` is strictly LOSSIER than plain `bd show`, and it fails in the
most alarming direction available.** Plain `bd show <id>` prints a `COMMENTS`
section carrying every comment body; `bd show <id> --json` returns
`comment_count` and **no `comments` key at all**. Measured 2026-08-21 on
`bd-ib-1w1h`: the plain form renders the full comment, the `--json` form emits
15 keys and none of them is `comments`. So an agent that writes a handoff
comment and then reads the record back through `--json` — the obvious
verification, and the one the plan prose explicitly asks for — finds no comments
and concludes **the write was lost**. It was not. Use `bd comments <id> --json`,
which returns the bodies; `_beads_client.py`'s `list_comments` docstring has
said so all along, but a docstring is not a surface a hand-driving operator
reads. Note also that `bd show --json` returns a **one-element array**, not an
object, so `payload["id"]` raises rather than returning the id.

**And the comment body lives under `text` — NOT `body`, and NOT `content`.**
This is the tail of the trap above and it defeats the remedy the paragraph
just prescribed, which is why it belongs here rather than as its own entry.
An agent that follows the advice, reaches the right verb, and then indexes
the wrong key gets an EMPTY STRING PER COMMENT — the identical observation
to the loss it was checking for, and equally silent. Measured 2026-08-22 on
`bd-ib-vfsg`: a 3,021-character comment read back through an accessor
reaching for `body` rendered as nine empty comments; the same records
carry keys `author`, `created_at`, `id`, `issue_id`, `text`, and the text
was never anywhere but present. Note that the sentence above SAYS "bodies",
so this file's own wording is what points at the wrong key. Two sessions hit
this independently on 2026-08-22, one of them while writing up the other's
instance, so treat it as structural rather than as one agent's slip. The
discriminator is the one this catalogue already prescribes for a surprising
empty result: dump the raw JSON and PROVE THE KEY SHAPE before treating an
absence as a finding — `sorted(record.keys())` settles it in one line.

**`bd update --metadata` MERGES AT THE TOP LEVEL AND REPLACES NESTED OBJECTS
WHOLESALE — so a nested sub-key you did not resend is GONE, while a top-level one
you did not resend survives.** This asymmetry is invisible in any single write and
it decides how much data an incident actually lost, in both directions. Measured
2026-08-22 on this tenant with two throwaway records: starting from
`{rank, unmodeled_top_level, audit{...}}`, a write of `{"rank": ..., "probe_key":
...}` returned `{rank, probe_key, unmodeled_top_level, audit}` — the two keys
absent from the payload were untouched. But a write that DOES include `audit`
replaces that whole object, so every sub-key of it that the payload omits is
destroyed.

The practical consequence, which is what makes it worth a catalogue entry: a
caller that reads metadata, edits one nested field and writes the nested object
back is performing a read-modify-write that only preserves what it happened to
carry, while the same caller doing the same thing at the top level is safe.
Nothing in the output distinguishes the two.

This is the real mechanism behind `bd-ib-h2zj`, and knowing it CORRECTS that
item's own account: it attributed the loss to the Python side rebuilding the
whole metadata dict, and concluded that unmodeled keys die "at the `audit` level
or the metadata top level". Measured against the pre-fix build on the live store,
`audit.supersedes` was destroyed and `unmodeled_top_level` survived the identical
close. The Python side does rebuild the dict; what reaches the database is
governed by bd's merge, which the reasoning had not accounted for. So an audit of
this tenant for silently-lost provenance should hunt NESTED keys and can ignore
top-level ones. (The fix in PR #1701 now preserves both, which is the right place
for the guarantee — bd's merge semantics are not ours to depend on.)

**Records are `omitempty`-sparse, so A MISSING KEY IS NOT EVIDENCE OF LOSS.**
This one is different in kind from the rest of this catalogue: it produces a
WRONG CONCLUSION FROM A CORRECT OBSERVATION, which is why cross-checking does
not catch it. `bd`'s Go serializer omits any field holding its zero value
rather than emitting `null` or `[]`. Measured 2026-08-21 across all 523 records
of the `livespec-dev-tooling` tenant: 25 distinct keys appear and only **10**
appear on every record — `labels` on 243, `metadata` on 183, `dependencies` on
194, `notes` on 155, `parent` on 116, `acceptance_criteria` on 65,
`design`/`spec_id` on 7, `external_ref` on 4. A grooming pass saw `labels`
absent on 280 of 523 records and reasonably concluded the listing had dropped
them. **It had not.** Control, run three ways, each designed to return the
opposite answer if the listing were lossy — server-side `--label` count versus
client-side count from the listing: `intake:triaged` 69/69, `origin:freeform`
201/201, `needs-regroom` 3/3, symmetric difference **0** in every case; and
`--all` versus `--status all` compared record by record across all 523 gave
identical id sets with **zero** records whose `labels` differed. The records
without the key genuinely carry no labels. Knowing the encoding convention is
the whole defence. There IS a real way to lose labels — the `--skip-labels`
flag, whose own help text reads "The labels field in output will be empty
regardless of actual labels" — so know it exists, and know that **nothing in
the normal path passes it**.

A SECOND WORKED EXAMPLE, on a field nobody had recorded this trap for, because the
label case above can read as a quirk of labels. `overseer-qruxr7` in the
`livespec-overseer` tenant shows `acceptance_criteria` ABSENT from its raw JSON
record entirely, while its `metadata` holds an 856-character
`acceptance_criteria`. A sibling filed minutes later, `overseer-au3pt3.11`, shows
the mirror image — native `acceptance_criteria` of 1,284 characters and empty
metadata. TWO SESSIONS INDEPENDENTLY concluded the filing path had LOST the
criteria, and therefore that a dispatch of that item would arrive with nothing to
evaluate and silently pass a no-op acceptance. That conclusion was wrong. `store.py`
builds `content_fields = {**metadata, **record}` — a MERGED read with native winning
— so a metadata-held copy is read normally, and through the sanctioned projection
both items report their criteria in full (856 and 1,284 characters). The two records
differ only because a five-week-old cached plugin build wrote acceptance into
metadata where today's build passes it natively. Nothing was lost in either.

**An instrument that CANNOT RETURN A HIT, reporting no hits.** This is the sibling
of the sparseness trap above and it sits one level earlier: there the observation
was correct and the conclusion wrong; here THE QUERY ITSELF WAS INCAPABLE OF FINDING
THE THING, and it reported a clean negative with no error. Every instance below
returned valid output, exit 0, and a plausible answer.

The sharp form of the rule, which is what makes it usable: **a control that
establishes an instrument FUNCTIONS is not a control that establishes it is POINTED
CORRECTLY.** The second needs its own positive case — a query that SHOULD return
something, returning it. The discriminating question for aim is therefore: *what
should this query return if it is pointed correctly, and does it?*

Measured instances from 2026-08-21 and 2026-08-22:

- **An anchored regex that cannot match the real line.** Claim: "`bd update` has no
  `--description` flag, so a description cannot be edited non-interactively."
  The pattern was anchored `^\s+--(description|acceptance|notes)`; the help line
  reads `-d, --description string`, leading with the SHORT flag, so a two-dash
  anchored pattern can never match it. Three routes existed (`-d/--description`,
  `--body-file` with `-` for stdin, `--stdin`). The same shape recurred within the
  hour: a ten-repo sweep for `sorted(children)[-1]` — a PARAPHRASE reconstructed
  from a peer's prose — returned zero while two live instances existed as a
  multi-line `sorted(...)` assigned to `matches`, then `matches[-1]`.
- **A wrong-target query with a confident empty answer.** Claim: "no fabro run
  exists for either dispatch." The query was `fabro ps`, which defaults to the LOCAL
  server, while the Dispatcher submits with `--server https://hp-xubuntu…`. Both
  runs were alive on that host. The local query returned 725 rows — a large,
  healthy, entirely irrelevant population. The discriminator was not a better run
  query but PROCESS ANCESTRY: the live `fabro run` process carries `--server <host>`
  in its own cmdline, which NAMES the target instead of assuming one.
- **A PATH false-absence**, hit by two sessions independently. Claim: "fabro is not
  installed." It is; the credential wrapper does not carry it on PATH. Preserve PATH
  explicitly.
- **The most credible one, because the instrument was demonstrably healthy.** Claim,
  reached independently by two sessions: "there is no local route to a remote run's
  store, so `fabro dump` cannot rescue an interview-destroyed run." The control that
  was run was a GOOD control — `fabro ps -a` returned 726 rows, proving the binary
  works, the query shape is valid and the store is readable. It proved the instrument
  FUNCTIONED; it could not prove the instrument was AIMED at the right host. Every
  zero collected was equally consistent with "this run does not exist" and with "I am
  querying the wrong store", and nothing in the output distinguished them. Falsified
  by execution: `fabro dump <run> --server https://hp-xubuntu… -o <dir>` exported 34
  files including `stages/002-implement@1/diff.patch` at 21,949 bytes — the very
  artifact the rescue procedure is written around. Re-confirmed independently on run
  `01M0H73GQ8Y0`: `dump --server` exported 61 files, and `attach --server` reached a
  run genuinely holding a human gate, rendered its prompt and accepted an answer. The
  remedy was fully operative the whole time, and defects were filed against a
  capability that already worked.
- **Docker measured through the wrong storage root.** Claim: "Docker cannot be
  filling the factory disk." The measurements were aimed at `/var/lib/docker` and
  were CORRECT — two independent sessions saw small values (12M and 4.3G), and a
  post-cutover check on the same host saw `/var/lib/docker` at 1.8M. The population
  was wrong: on Docker 29 the image bytes live in `/var/lib/containerd`, which
  measured 28G on the same host. A small `/var/lib/docker` reading therefore
  exonerates the wrong tree while the factory is out of room. Do not rely on
  `docker system df` on a large store; it can hang. A whole-tree `du` can time out
  too. Bisect per-subtree under `/var/lib/containerd`, and treat the subtree that
  never returns as the finding rather than as an absence.
- **A rebase-merged PR read through its series tip.** This repo rebase-merges, so
  the merge SHA is the LAST COMMIT OF THE REBASED SERIES, not a merge commit that
  contains the series. `git show <merge-sha>` therefore renders exactly one commit
  and SILENTLY OMITS the rest of the PR — no warning, no indication that earlier
  commits exist. Measured 2026-08-22 on PR #1736: the fix for `bd-ib-2os2` landed
  in the FIRST commit, `3377f7d4` (shell-aware command-position matching), while
  the PR tip `6c776441` was unrelated hardening. A `git show 6c77644...` read
  concluded "the merged diff does not address the filed defect at all", a false
  negative that would reopen settled work and re-dispatch a closed item. The
  discriminator for "what does this PR contain?" is the PR's commit list
  (`gh pr view <n> --json commits`), but that is the WRONG instrument for "what
  actually landed on master?" Verifying a landing by commit SHA is verifying the
  wrong identity: under rebase-merge, PR/branch SHAs do not survive. Measured
  2026-08-22 on PR #1776: `git branch -r --contains ac7ebb0f` returned
  `origin/master` for the merge-sha control, while the same command returned ZERO
  for each branch SHA `90d094df`, `eaaa24ab`, `10f0b4a0`, and `60a16fb7`. Master
  carried three `fix:` commits under new hashes (`ac7ebb0f`, `36026f97`,
  `89997f93`), and the four `fabro(<run-id>): <stage> (succeeded)`
  stage-checkpoint commits were absent entirely. So a PR's commit count is not
  master's commit count either. Use the PR commit list only to read what the PR
  contains. To verify the landing, use a CONTENT check that survives a rebase,
  such as `git show origin/master:<path> | grep -c <token>`, or a master-side
  range read such as `git log <base>..origin/master`. This was caught by a peer
  session on the report that landed the original trap entry: the author had also
  run a "positive check on the substance rather than the shape", and that content
  check was the load-bearing proof.
- **A killed run presumed to have lost work that it had already published.** A
  Fabro run that parks on a human gate and is later killed leaves an item stranded.
  The natural conclusion — "the sandbox is gone, so the work is gone" — is right
  only when the run had not yet published, and nothing in the stranded item
  distinguishes the two. Measured 2026-08-22 on `bd-ib-2os2`: the claim-release
  comment recorded "expected to start from scratch. Any unpublished work in the
  dead sandbox is gone." Run `01M0KXYZRWXNF7SSRN2KHJ57DK` had in fact published PR
  #1736 — implement, janitor, review and disposition stages all `(succeeded)` —
  before parking, and re-dispatch found and merged the PR in five minutes. The
  discriminator is a forge search for a PR carrying the run id before
  re-dispatching a killed or stranded run; the run id is stamped into its commits.
  `bd-ib-6o6h` is the genuine-loss counterpart, `bd-ib-2os2` is the survived case,
  and one query separates them.
- **A mutation that never applied, reporting as a surviving mutant.** This belongs
  here because it is the same "query incapable of returning the hit" failure in the
  test harness itself. While mutation-checking `storage-reclaim.test.sh` on
  2026-08-22, `sed` patterns silently matched nothing, so three of five mutants ran
  against an unmodified script and reported `50 passed, 0 failed` — exactly the
  same surface a genuinely surviving mutant would produce. The discriminator is
  not the suite result; the harness must prove the mutation landed, for example by
  appending a `grep -c` or equivalent content check that would be nonzero only
  after the edit. The same rule applies to guard tests: isolate the arm being
  guarded. A "live process in a subdirectory" case that also has a live process at
  the worktree root still passes after the subdirectory arm is deleted.
- **A hand probe filtered out the state it was trying to disprove.** While checking
  a claim that a blocked Fabro run was never reaped, `fabro ps -a | grep -iE
  "blocked|RUN ID"` returned no cited run and produced the wrong report that the
  run was "no longer listed on hp at all". The run had already reached `failed`, so
  a filter on `blocked` could never return it; the proper measurement found it in
  `ps -a` with a terminal status at `240m00s`. The mirror failure happened in the
  same audit: probing this item's text for the retracted phrase "never reaped"
  found a real hit inside the retraction narrative and nearly turned a quotation
  into a false correction. A count is not a verdict in either direction. Absence
  does not prove the claim is gone, and presence does not prove it is asserted.
  Discriminate by position and context: for panes, key on the tail region where a
  live picker renders its footer; for prose, read the surrounding sentence to see
  whether the hit is a claim or a quotation. This is the same family as
  `livespec-overseer`'s `overseer-i6eu2k` shipped-detector defect, but these two
  were ad-hoc verification lapses with no code to fix, so cite the family rather
  than widening that item.
- **An instrument so slow that its own observation changed the answer.** This is
  adjacent to wrong-population probes but not identical: the instrument was aimed
  at the right population, and that population changed while the instrument was
  looking. Measured 2026-08-22, the storage-reclamation liveness guard forked
  `readlink` once per process per worktree: 1,727 process entries, 27.5 seconds for
  one call, 608 worktrees, over one million forks, and a projected 4.6-hour scan.
  The scan outlived the fixture's own sleep, so the subject exited before the
  answer arrived. The discriminator is: does this measurement take long enough for
  the subject to change underneath it?
- **Partial output from a still-running job is not an outcome.** This is folded
  here because it is another healthy-looking observation aimed at the wrong
  question. During the same storage-reclamation dry run, output stopped after the
  LEG A header with `sort: write failed: Broken pipe`; the first conclusion was
  that LEG A had died, and the second was that the script was fine. Both were
  wrong. The job was still running, 25 minutes into the 4.6-hour scan above, and
  there was a real guard defect, just not the broken-pipe line. The discriminators
  are separate: a process that has not exited has not reported its outcome, so
  "output stopped" and "process died" are different claims; and the broken pipe was
  cosmetic for `find | sort -rn | head -1`, because `head` exits first and `sort`
  takes EPIPE. That pipeline was verified over 60 real worktrees, 60/60 valid.

**The existing "state the scope you searched" rule is necessary and NOT sufficient**
— see "Verification discipline (repo-additive)" below, whose Rule 1 this extends. In
the anchored-regex instance the scope was stated and correct (ten repos, every `.py`,
exclusions named) and the sweep was still worthless, because the PATTERN could not
match. State the scope AND establish that the instrument could have returned a hit
within it.

Why this one is worth re-deriving before acting: an "I checked and it is IMPOSSIBLE"
conclusion FORECLOSES THE ACTION, and nothing downstream ever re-tests it. A wrong
measurement gets contradicted by the next reader; a false impossibility just quietly
stops being examined. In the anchored-regex instance the fix was one command away, and
the false conclusion was passed to two other sessions as advice before being caught.

**Classify a flaky safety test by the direction it fails before dismissing it as
noise.** This is its own entry because the actionable rule is about deletion risk,
not search shape. Measured 2026-08-22, `storage-reclaim.test.sh`'s liveness case
failed 2 runs in 3 on a load-71 box and looked like a fixture race. It was the guard:
`readlink /proc/<pid>/cwd` printed the target while `worktree_is_live` returned
not-live, 5 of 5 attempts. A liveness guard failing toward NOT-LIVE permits a
deletion. That is the expensive direction, and environmental noise only made the
wrong guard look like a flaky test.

**When two honest measurements disagree, the difference is the data.** This is not
folded into the wrong-population catalogue because neither instrument is the
villain; they answered different questions correctly. Measured 2026-08-22 on the
factory host, `du -xsm /var/lib/docker` returned 3M while `du -sm /var/lib/docker`
returned 2055M. Read as a 700x under-report, that would be a false defect against
the size helper. The divergence localized to one subdirectory on another device,
and `df` settled the intended reclamation question: `-x` is correct when asking
"how many bytes does deleting this tree free on this filesystem", not "how large is
this mounted tree including other filesystems". Before believing either number,
locate the difference with an independent instrument such as `df`/`findmnt`.

**The `dependencies` array is ONE HETEROGENEOUS LIST whose target key DEPENDS ON
THE SURFACE THAT PRINTED IT, and the majority of its rows are not blockers.** On
`bd list --json` a row keys its target `depends_on_id`, with the edge in `type`;
it is not `target` or `to`, so a naive accessor yields `None` and a tenant of
perfectly sound edges reads as a tenant of dangling ones. Worse, six edge types
share the single array.

**Do NOT read that as "the target key is never `id`" — this entry asserted exactly
that until 2026-08-30, and the absolute form is what made it dangerous.** On
`bd show <id> --json` the rows are a DIFFERENT SHAPE: each inlines the whole target
record and keys it `id`, with the edge in `dependency_type`. So an accessor written
from this catalogue's own prescription reaches for `depends_on_id` on a `show` row,
gets `None`, and reports a live edge as dangling — the identical wrong conclusion
this entry exists to prevent, produced by obeying it. Measured 2026-08-30 on this
repo's tenant: all 500 dependency rows in `bd list --status all --json` carry
`depends_on_id`+`type` and none carries `id`+`dependency_type`, while `bd-ib-dbzp`
read through `bd show --json` carries `id`+`dependency_type` and neither
`depends_on_id` nor `type`. Each reading is correct for its own surface; neither
generalizes. The discriminator is the one this catalogue already prescribes for a
surprising empty result — `sorted(row.keys())` before indexing, which settles it in
one line. Measured 2026-08-21 over all 261 dependency
rows in the `livespec-dev-tooling` tenant: `parent-child` 116, `blocks` 93,
`relates-to` 26, `discovered-from` 23, `related` 2, `duplicates` 1 — so **168 of
261 rows (64%) are NOT blockers**, and any filter treating the array as a
blocker list is wrong for the majority of its own input, in the direction of
INVENTING blockers that do not exist. Do not hand-roll the discrimination:
`commands/_plan_child_edges.py` already does it correctly, and
`list-work-items --json`'s `depends_on` projection is **blocks-only** (verified
on `bd-ib-3kolea.2`, whose raw edge list is one `parent-child` plus four
`blocks` and whose projected `depends_on` is exactly those four).

**Prefer `list-work-items --json` to any raw per-item JSON read.** The
projection is DENSE — measured 2026-08-21 on this repo's tenant, 30 keys
present on all 638 records, no `omitempty` sparseness — so trap 2 does not
reach it, and it discards `parent-child` from `depends_on`, so trap 3 does not
either. Since `bd-ib-m36re3` it also carries `parent` and `labels`, which is
what makes the roll-up and acceptance-split questions answerable without
dropping to raw. **One caveat, so this does not become a new trap:** its
`parent` is populated from the native field and the `parent-child` EDGE, so it
inherits the dotted-id blind spot described in the child-enumeration entry
above. It is the right surface for reading an item's parent; it is still NOT a
complete child enumeration. Use `undisposed_plan_child_ids` /
`client.children()` for that.

**Query the ledger for prior art BEFORE designing a fix — reading the source is
not sufficient.** Scan every item — **including `closed` ones** — for the defect
class you are about to
design for, and read the FULL description of anything that overlaps: maintainer
rulings and explicitly rejected options are recorded there and are binding
context. **Include `acceptance` and `blocked` items, not just `backlog`** —
parked items are where shipped-but-unaccepted work hides, which is precisely what
a source-only reading cannot see. **`closed` items matter just as much**, because
that is where "this was already built" and "the maintainer already ruled on this"
live; a prior-art scan that skips them re-litigates settled work. This means the
scan MUST use `--status all` per the survey note above — the bare `bd list` form
cannot see closed items at all. (Cost of skipping THIS, 2026-08-19: a session
filed a restore-test finding against `dolt-server` reporting "no prior art",
having surveyed 4 of that tenant's 72 items with the bare form. The real prior
art — `dolt-server-ckue2g`, a closed Phase 2 item recording an end-to-end
validated restore pipeline — was invisible to the command it had been told to
use, and the filed item had to be corrected after the fact.) Treat each filed item as a claim with a
timestamp, not as fact; verify its specifics against the forge before relying on
them. (Cost of skipping this, 2026-07-26: the `dispatch-claim-liveness` thread
verified the code exhaustively, published two design recommendations to a durable
handoff on `master`, and had to retract both — `bd-ib-lza6` sat in `acceptance`
having already shipped the `reconcile-merged` valve that one recommendation would
have broken, and a filed item asserted a dispatch produced "no PR" when its PR had
in fact merged.)

**Write acceptance criteria as `- ` bullets, one assertion each, ending in a
period — and verify the parse before filing.** The evaluator grades the
criteria field one gradeable assertion at a time, and `criteria_lines`
(`commands/_dispatcher_acceptance_criteria.py`, since `e4db2e5d`) segments by
CONTENT, not by line: only a blank line, a list marker, or a header starts a
block, and each block is then split into sentences. A flush-left line with no
marker CONTINUES the previous block, so the older advice here — "one unwrapped
assertion per line" — now produces the opposite of what it promises. Measured
2026-08-31 on `bd-ib-6up7oj`: nine plain lines with no markers and no terminal
periods parsed as ONE assertion; the same nine as `- …` bullets each ending in
a period parsed as nine. Keep explanatory prose, rationale, and provenance in
the description or a comment, and do not write negative criteria ("no file
contains X") — the judge passes on literal diff vocabulary and a negative has
none. Check the result with `effective_criteria(item=...).parse_display()` (the
capture and groom front-ends print it) and apply all of this at FILING time,
because the evaluator reads the dispatch-time criteria snapshot, so editing an
item mid-run cannot rescue an in-flight dispatch. The underlying defects and
measurements are tracked in `bd-ib-tfpdya` and `bd-ib-5z0g`.

**And keep every criterion inside the MERGED DIFF'S OWN VOCABULARY — a criterion
naming an artifact the diff never mentions cannot pass, however true it is.**
This is the sibling of the rule above and it defeats that rule's remedy: the line
can be a single, unwrapped, genuine assertion and still fail. `_judge_criterion`
passes a criterion when ANY of its significant terms appears literally in the
normalized merged diff (the mechanism `bd-ib-5z0g` records), so a criterion whose
subject is a `SPECIFICATION/` scenario, a plan file, or a sibling work-item fails
with `insufficient merged diff evidence` — the SAME string a genuinely unmet
assertion produces, which is why it reads as a real defect rather than as a
mis-aimed instrument.

Measured 2026-08-26 on `bd-ib-ujihbw.2`, merged as PR #1867: ten of eleven
criteria passed on merged-diff evidence and the eleventh — "Scenario 83's two
scenarios pass against the implementation." — failed TWICE, burning BOTH
`acceptance_rework_cap` attempts on correct, already-merged work. Rewording it to
drop its cross-item demand changed NOTHING, because it still named the scenario
and so still had no diff vocabulary; only REMOVING the reference works. The
control is clean: `bd-ib-ujihbw.1` and `bd-ib-ujihbw.3` carry ZERO scenario-naming
criteria and both passed acceptance and closed on their first pass.

So never put a `## Scenario NN` reference in the acceptance-criteria field of a
factory-dispatched item. Scenario traceability belongs in the description, and
binding a scenario heading to an exercising test is its own integration-tier
deliverable (`bd-ib-w3if5j` for the v071-v079 range), never a by-product of the
implementing item. Note the second-order trap, because it is the expensive half:
when the item that owns the binding must land LAST — its closing criterion being
that no coverage entry still names it — an implementing item whose criteria demand
that binding is unsatisfiable in BOTH directions, and no re-dispatch can break the
circle. The live defect class is `bd-ib-99a1`.

**Before IMPLEMENTING an item, read its comments — `bd show` does not carry
them.** The rule above is about scanning the ledger for prior art. This one is
narrower and catches a different miss: RIDERS ARRIVE ON A WORK-ITEM AFTER IT IS
FILED, they are binding scope, and NEITHER the description NOR the
`acceptance_criteria` field announces that any exist. `bd show <id>` renders a
`COMMENTS` section, but `bd show <id> --json` carries only `comment_count` (see
the beads-trap catalogue above), so an agent reading an item through the machine
surface sees no sign of them at all. Run `bd comments <id> --json` on the item you
are about to build, not just `bd show`.

*Cost of skipping this, 2026-08-21:* `bd-ib-cfncp5` was implemented and merged
covering THREE traps when three riders — filed at 01:10:09Z, 01:43:27Z and
01:55:34Z, all before the work started — had raised it to FOUR and supplied a
sharper formulation for the fourth. The implementing session read the description
and the criteria, rewrote those criteria with the item open in front of it, and
still never read the comments; its rewrite then encoded "all three traps" as the
bar, locking the omission into the very field acceptance is judged against. It
took a second pull request to finish, and the miss was caught by a peer session
rather than self-announced. Note the shape: the session's own verification grepped
merged `AGENTS.md` for the three trap markers it knew about, found all three, and
passed — an instrument pointed at the wrong population, which is exactly the fourth
trap in the catalogue above.

**Ledger text can permanently destroy an item's dispatchability.** The rendered
run goal is assembled from the item's title, description, acceptance criteria,
notes, lessons and ledger comments. A safety check scoped only to the obvious
title / description / acceptance trio can therefore pass an item whose later
goal render is already poisoned. Run this check before dispatching, and before
commenting on any item that discusses templating:

```bash
python -c 'import json, subprocess, sys; issue=sys.argv[1]; fields=json.loads(subprocess.check_output(["bd","show",issue,"--json"], text=True))[0]; comments=json.loads(subprocess.check_output(["bd","comments",issue,"--json"], text=True)); needles=(chr(123)+chr(123), chr(123)+"%", chr(123)+"#"); hay="\n".join(str(fields.get(k,"")) for k in ("title","description","acceptance_criteria","notes","lessons"))+"\n"+"\n".join(str(c.get("text","")) for c in comments); hits=[n for n in needles if n in hay]; raise SystemExit(("template opener present: "+repr(hits)) if hits else 0)' <item-id>
```

An opener anywhere in that assembled text has two bad outcomes: the dispatch can
die before any Fabro run exists, with an error that names the workflow file and
reports a line number that is really an offset into the generated goal; or, if
the restored token happens to be valid, it can silently rewrite the brief with
no error. Ledger comments make this permanent: `bd comments` offers add and
list, with no edit or delete, so a poisoned comment can only be escaped by
filing a clean-text successor item. The trap fires on prose about itself; quoting
the failing evidence verbatim is good incident filing practice and is exactly
what destroys the record. Three records have already been lost this way.
To write about the token safely, substitute U+27E6 for the literal open
interpolation pair and U+27E7 for the literal close pair, and state on the
record that this substitution is in force. This convention is owned by
`livespec-dev-tooling-9yb4`, so the fleet converges on one form rather than
private notations. It matters most in LEDGER COMMENTS, because a comment cannot
be repaired after the fact.
`bd-ib-ai9a` is the live P1 carrying the mechanism and Fabro-side fix, and
`bd-ib-pgne` is the orchestrator-side pre-flight refusal.

**A long-lived session dispatches through the plugin build it STARTED with, not
the build its repository resolves — and the failure reads as a factory outage.**
A Claude Code session binds `CLAUDE_PLUGIN_ROOT` once, at start. `claude plugin
update` and the SessionStart hook move the registered install underneath it,
and nothing re-points the running session except a restart or a human-typed
`/reload-plugins` (`bd-ib-97v4`: the update remedy cannot move a running
session). Measured 2026-09-06: the `overseerd` session, started 2026-09-03,
dispatched `overseer-qt3wvu.1` through cache build `d709f27ac3c1` (v0.124.1,
2026-08-31) — the one installed build that templates the sandbox prepare steps
(`39526e5c`) but predates the host-side substitution fix (`79066c79`,
`bd-ib-8atx`, released v0.124.3 on 2026-09-04) — while livespec-overseer's
registered install was already v0.129.1. The run died at setup command index 1
on a literal template opener, exit 127, and the session recorded "the whole
livespec-overseer lane is down" on the ledger; hp had completed four
livespec-overseer runs that same day. The discriminator is the SUDO JOURNAL,
which records the full `drive.py` / `dispatcher.py` path and therefore NAMES
the build (journal timestamps are local, +02:00 against a run's UTC):

```bash
journalctl --since "<t1>" --until "<t2>" -o short-iso _COMM=sudo | grep -E 'drive.py|dispatcher.py'
git merge-base --is-ancestor <fix-sha> <cache-hash> && echo fixed || echo NOT-fixed
```

The dispatcher now journals a `dispatcher-registered-install-lag` warning when
the executing build is older than the target repository's registered install
(`_dispatcher_registered_install_currency.py`). It is surfaced, never enforced,
per the ratified currency contract, so READ the dispatcher stderr the `drive`
result carries before concluding anything about the factory. The remedy is per
session: restart it, or invoke the registered build's `scripts/bin/` entry
point by explicit path. To REFUSE a known-broken build range outright, commit a
`dispatcher.minimum_release` floor in the target repository's `.livespec.jsonc`.
Second-order trap, same incident: the failure write-up quoted the literal
opener into the item's own comment, which is exactly the poisoning case above —
file such a failure with the U+27E6 / U+27E7 substitution, never verbatim.

## Host Fabro server (self-hosted dark factory)

The Dispatcher's host-direct path (`dispatcher.py loop` run on the host, NOT in
the orchestrator container) connects to a long-lived Fabro server on
**`127.0.0.1:32276`**. Installing the plugin does NOT start it; the maintainer
runs it directly from `~/.fabro/bin/fabro`. As of 2026-07-30 the host binary is
`fabro 0.254.0 (8de6611)`, built from **`factory-integration`** — the ONE standing
branch in our fork (`thewoolleyman/fabro`) that carries every fabro fix the
factory needs but upstream has not released (today: PR #568 credential refresh,
the env-configurable daemon-readiness timeout, PR #552 configurable checkpoint
git timeout, PR #576 OTLP export transport, the fork-local O1 worker-OTLP env
re-injection + O2 W3C-traceparent join that light that transport up for the Codex
era, the fork-local P2 that decouples OTLP export from `FABRO_LOG` so quieting
logs cannot silently zero telemetry, and the fork-local O4 `run_turn` ACP turn
span that makes per-turn command/stop-reason queryable).
Never pin a fabro build from any other branch, and never modernize the base: any
fabro ≥ 0.256 breaks `workflow.fabro` (fabro #474 de-templates `acp.command`, so
every dispatch dies `exit 127`). These rules are NORMATIVE — `SPECIFICATION/constraints.md`
§"Fabro runtime constraints" (ratified in `v035`). The build/pin/rollback commands are in
`orchestrator-image/README.md`. Rollout/revert state is ledger `bd-ib-2nq.4`
(currently dispatchable; its parent `bd-ib-2nq` is poisoned by ledger text and is
not the dispatch target); deferred modernization is `bd-ib-6qu` (currently
undispatchable because both its description and an append-only ledger comment are
poisoned).

**THIS REPO'S DISPATCHES DO NOT GO TO `127.0.0.1` — check the configured factory
before concluding a run is missing.** The local server described in this section is
real and is what `sudo systemctl restart fabro-server` manages, but
`.livespec.jsonc` sets `dispatcher.default_factory` to **`hp`**, and its
`dispatcher.factories` block defines only two targets, neither of them loopback:
`hp` = `https://hp-xubuntu.perch-rudd.ts.net:32276` and `vps` =
`https://vps.perch-rudd.ts.net:32276`. The Dispatcher passes the resolved factory's
URL to `fabro run --server`, and an item can override the choice through its own
`dispatch_factory` metadata key.

The practical consequence, measured 2026-08-21: a bare `fabro ps` defaults to the
LOCAL server and reports `No running processes found` while this repo's dispatch is
perfectly healthy on `hp`. That is a clean, plausible, wrong answer with no error —
an instrument aimed at the wrong host, per the fourth trap in the beads-trap
catalogue above. Pass the factory explicitly:

```bash
~/.fabro/bin/fabro ps --server https://hp-xubuntu.perch-rudd.ts.net:32276
```

The same applies to `inspect`, `dump` and `attach`, all of which accept `--server`
and all of which reach a remote run's state when given it — verified on run
`01M0H73GQ8Y0`, where `dump --server` exported 61 files and `attach --server`
reached a run holding a live human gate and answered it. Concluding that a remote
run is unreachable because a bare invocation found nothing is the same trap one
level on.

**A Fabro run being `blocked` does not mean the work is incomplete.** This gets its
own Fabro-section entry because the discriminator is operational: use
`fabro inspect --server <factory> <run>` before attaching or reaping. Measured
2026-08-22, run `01M0MC8FFXEH` sat `blocked` for 65 minutes while `inspect` showed
implement complete and review succeeded with `preferred_label=approve`; only the
`pr` stage was blocked, on a non-fast-forward rejection against the branch the same
run had already pushed before rebasing (`bd-ib-e3xm`). A human gate had no useful
answer to give, and Retry could only meet the same rejection.

The invisible end state is reviewed work published on a branch with no open PR. It
is not unpublished, so an unpublished-work reap watcher does not fire; it is not a
PR, so forge queries keyed on pull requests miss it; and it disappears from
ordinary `fabro ps` once the run exits. A blocked run does eventually reach a
terminal status, and `fabro rm` refusing one without `--force` proves only that it
has not reached that point yet. The discriminator between a run that ended on its
own and one a human removed is `fabro ps -a`: the former remains listed with a
terminal status, while `fabro rm --force` deletes it from `ps -a`.

**But do NOT read that terminal duration as the moment the run was reaped or its
scheduler slot came back. CORRECTED 2026-08-22 — this paragraph originally said
the opposite, and the retraction is the point.** It cited run `01M0KXYZRWXN`
"self-terminating exactly at `240m00s`" as proof a configured ceiling had fired,
treating the ROUNDNESS as evidence the mechanism acted. That inference is
inverted. **An exact round number is the signature of a CONSTANT, not of a
measurement:** it tells you what was configured and never that the configured
thing did anything.

Measured first-hand on 2026-08-22. That run's `conclusion.timing.wall_time_ms` is
`14400071`, which reproduces this repo's own `implement` node `timeout="14400s"`
(`.claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro`) to 71
milliseconds — the duration IS the timeout constant. Every per-node
`wall_time_ms` on the same record is `0`, so the record carries no independent
timing to check it against. The control settles it: `01M0M9AHRXEX` in
`livespec-overseer` is terminal at exactly `360m00s` — the SAME
`ImplementWorkItem` workflow, a different repo's configured timeout. If 240 were
a fleet-wide ceiling, 360 could not exist. (A peer session reports the run's
container had been dead roughly 52 minutes before that value was written; that
part is cited here, not verified here.)

WHAT IS NOW OPEN, and it is worth more than the retracted claim: if the recorded
duration is a constant stamped at finalisation, then **a run's own record cannot
tell an operator when its capacity actually returned** — slot accounting keyed on
that number reports a figure nobody can act on. That question belongs to
`bd-ib-rnlks6` (a blocked run holding its scheduler concurrency slot), NOT to the
storage-reclamation epic whose child originally recorded this paragraph: that
epic governs disk headroom, and a scheduler slot is not disk.

**Factory ENOSPC is a FACTORY-HOST failure, not an item failure.** The signature
measured on 2026-08-22 is: `drive.py` exits 1, the dispatcher exits 1, the failed
stage is `fabro-run`, no Fabro run is created, a phantom claim is left behind, and
the error detail names `ENOSPC` on a storage path that the dispatching machine
cannot see. The discriminator is the path: `/home/cwoolley/...` named the factory
host user while the dispatching machine was `ubuntu`, so local `df` and local
process views were clean but irrelevant. The failure happens before
item-specific processing, so no property of the work item can cause or avoid it.
Check disk on the selected factory host itself:

```bash
ssh <factory-host> df -h /
```

The blast radius is every repo routed to that factory, not the one item that
reported first; on 2026-08-22 two different repos failed with this signature
within 44 seconds. If a second declared factory is available, route the dispatch
there immediately, for example `--factory vps`, while the full factory cleanup
proceeds. livespec-overseer carries the phantom-claim list where this signature is
a sibling-repo update; route that update to livespec-overseer instead of editing
that repo from this one.

- **Start / restart** (OAuth-only — no wrapper, no `ANTHROPIC_API_KEY`):

  ```bash
  sudo systemctl restart fabro-server
  ```

  The canonical unit and installer live in the fleet repo
  `thewoolleyman/fabro-hosts`, at `services/fabro-server/` (moved out of
  `vps-info` on 2026-08-20, because `fabro-server` runs on both `vps` and
  `hp-xubuntu` and a per-host copy is what let the two diverge silently). One
  unit template plus a six-line `hosts/<host>.env` covers both factories, and
  `install.sh` refuses to apply one host's values on another. The unit runs Fabro in the
  foreground under systemd, passes the affirmative `--web` option, restarts it
  after failures and reboots, and refuses readiness unless `/runs` exists and
  the unauthenticated `/login` shell plus its JavaScript bundle load. Build the
  pinned fork with
  `cargo clean --release -p fabro-spa` followed by
  `cargo dev build --release -p fabro-cli`; the targeted clean prevents Cargo
  from reusing an assetless release embedding crate, and a plain `cargo build`
  does not refresh the embedded SPA. Never run `fabro server start` / `restart`
  directly on this host, because that bypasses supervision and the web-console
  readiness gate.
- **OAuth-only posture — do NOT put `ANTHROPIC_API_KEY` in the SERVER env.** It
  bills API cost and can leak into the sandbox. The agent's model auth is
  `CLAUDE_CODE_OAUTH_TOKEN`, injected into the *sandbox* by the Dispatcher per
  dispatch. In `fabro doctor`, `[✗] LLM Providers (none configured)` is therefore
  CORRECT.
- **Credentials live in `~/.fabro/`** (the GitHub App integration from the vault;
  `auth.json`; the SlateDB `storage/`). `fabro doctor` should show GitHub App
  **configured**; if it is not, the server's vault did not load — do NOT "fix" it
  by adding `ANTHROPIC_API_KEY`.
- **Fleet-shared + Tailscale-served.** `tailscaled` holds a standing
  `tailscale serve` proxy `https://vps.perch-rudd.ts.net:32276 → 127.0.0.1:32276`;
  it persists across restarts and simply returns refused while the loopback
  backend is down. The console URL is
  `https://vps.perch-rudd.ts.net:32276/runs`. A `:32276` listener owned by
  `tailscaled` (not `fabro`) means the proxy is up but the server is not.
- **Never `pkill -f 'fabro server'`** — it self-matches the killing shell and can
  reap unrelated shells. Match real daemons via `/proc/<pid>/exe` and kill by PID.
- **A merged factory slice stays `active` until you run `reconcile-merged
  --item <id>`; the `reconcile-runs.timer` does NOT close it.** The root
  timer runs `dispatcher.py reconcile-runs`, which reconciles only
  stranded/held runs and returns `reconciled: []` for cleanly-merged work.
  The active→closed valve on merge is a DIFFERENT subcommand driven PER
  ITEM: `dispatcher.py reconcile-merged --repo <repo> --item <id> --invoker
  <role:name>`. It runs the per-item post-merge janitor (fresh checkout +
  baseline checks — expect it to exceed a 600s foreground timeout; background
  it) and closes the item, printing e.g. `bd-ib-cwhos6  green at done PR#2146
  merged, post-merge janitor green`. Consequence: after a slice's PR merges,
  any downstream item blocked on it stays blocked until you run
  `reconcile-merged` for the merged item. Measured 2026-09-04 on
  `console-control-plane-primitives`: two merged slices sat `active` across
  four timer cycles (40+ min) until `reconcile-merged --item` closed each,
  which was what cleared their dependent's blockers. (Prior plan handoffs
  wrongly asserted the timer auto-closes a merged item.) Related: `next`
  never lists a `pending-approval` item, so an `admission:auto` item is
  invisible to `next` but selectable by the dispatcher drain, and `drive
  --action impl:<id>` admits and dispatches such an item in one step.

## Daily commands

- `just bootstrap` — first-touch setup on a fresh clone; idempotently sets
  `livespec.primaryPath`, installs the canonical commit-refuse hook at
  `.git/hooks/pre-commit` + `.git/hooks/pre-push`, installs lefthook hooks, and
  resolves plugin dependencies.
- `just check` — the full enforcement aggregate (lint, types, tests, coverage,
  AST checks). It is the load-bearing safety net; it runs locally, in pre-push,
  and in CI.

## Revise co-edit discipline — `tests/heading-coverage.json`

Every revise pass that adds, changes, or removes a `## ` heading in any spec file
MUST update `tests/heading-coverage.json` in the same change (via the revise
`resulting_files[]` mechanism) so the heading-coverage map stays in lockstep with
the spec. Diff the proposed `## ` heading set against the current spec file's H2
set; add an entry (`test` MAY be the literal `"TODO"` with a non-empty `reason`)
for each new heading, and drop entries for removed headings.

## Red-Green-Replay commit protocol

Product `.py` changes are committed via a 2-step single-commit TDD ritual,
enforced by the `red_green_replay` commit-refuse hook (it inspects the staged
tree and writes `TDD-*` trailers). The final result is ONE commit carrying the
test, the impl, and both trailer sets.

1. **Red commit.** Stage the test file ALONE — no impl — and commit with a
   `fix:`/`feat:` subject. The hook runs pytest on the staged tree; the staged
   test MUST fail on pytest (non-zero exit). An `ImportError` or a collection
   error counts as a failure to the hook, BUT you SHOULD prefer a genuine
   assertion failure so Red proves the behavior is actually unimplemented
   rather than merely unimportable — see the new-module stub technique below.
   It records `TDD-Red-*` trailers (test path, failure reason, test-file
   checksum, output checksum, captured-at).
   - Gotcha: the impl must be UNMODIFIED on disk at the Red commit, because the
     hook's pytest reads the on-disk module. If the impl already carries the
     change the test passes, and the hook rejects with `test-passed-at-red`.
2. **Green amend.** Stage the impl and run `git commit --amend`. The hook sees
   the `TDD-Red-*` trailers + the staged impl, re-runs the SAME test (now
   passing), and records `TDD-Green-*` trailers. The test file bytes MUST be
   byte-identical across the Red→Green pair; to change the test, author a fresh
   Red commit.

### New-module stub technique (avoiding false reds)

When the impl module under test does NOT exist yet, the natural Red would be an
`ImportError` or a collection error rather than an assertion failure. The hook
accepts that as a failing Red, but it does not prove the behavior is
unimplemented — only that the module is unimportable. To make Red fail on a
genuine assertion instead:

1. At Red time, create the impl module as a minimal **stub** on disk — enough
   that the test imports and runs, but its assertion FAILS (e.g. a function
   that returns a wrong/sentinel value, or raises `NotImplementedError` only
   when that still yields an assertion failure rather than a collection error).
2. The stub must NOT make the test pass — a passing test at Red trips the
   hook's `test-passed-at-red` gate.
3. Then the **Green amend** replaces the stub with the real implementation that
   makes the assertion pass.

This keeps Red honest: it proves the behavior is unimplemented, not merely that
the module is missing.

### Execution gotchas

Three failure modes that cost dispatched agents real time:

1. **Multi-test-file Red.** The Red commit must stage EXACTLY ONE test file
   (zero impl). The commit-msg `red_green_replay` hook rejects more than one
   staged test file with `multi-test-file`, AND lefthook's pre-commit only takes
   the fast coverage-skip Red path when `test_count == 1 && impl_count == 0`
   (otherwise it runs full `just check` and fails at <100% coverage). When a
   change needs multiple new/changed test files, stage only ONE at Red (a genuine
   failing assertion), then add the remaining test files + the impl + ride-along
   docs at the Green `--amend`. (The old `LIVESPEC_PRECOMMIT_RED_MODE` env
   override is gone.)
2. **Preserve the Red trailer block at Green.** On the Green `git commit
   --amend`, do NOT pass a fresh `-m` that overwrites the message — that wipes the
   inline `TDD-Red-*` trailers the hook wrote at Red. For a commit that touches a
   PRODUCT-IMPL path, the pre-push *range* replay check greps the FINAL commit body
   for BOTH `TDD-Red-Test-File-Checksum:` AND `TDD-Green-Verified-At:`; if the Red
   block is gone, the push is rejected. Use `--amend --no-edit` (or re-include BOTH
   trailer blocks). The Red and Green test-file bytes must stay byte-identical.
   **SCOPE — do not read this clause as unconditional:**
   `red_green_replay._commit_violates` derives `product_paths` from the same
   `_IMPL_PREFIXES` tuple the commit-msg leg uses and returns early when that list
   is empty, so a commit touching NO product-impl `.py` is EXEMPT from the
   both-trailers requirement rather than passing it. A dangling Red block on such a
   commit is harmless. NEVER hand-forge a `TDD-Green-*` trailer to satisfy a check
   that cannot fire — read `_IMPL_PREFIXES` and confirm whether your paths are even
   in scope before concluding you are blocked.
3. **Working-tree gate, not just staged.** lefthook's pre-commit runs the
   structural / dev-tooling checks over the WORKING TREE, not only the staged set.
   So "revert only the impl for Red" is INSUFFICIENT when the change also ADDS
   files that a working-tree gate inspects (e.g. a new structural check that
   asserts certain dirs are absent, while you've already created those dirs on
   disk). At Red, make the WHOLE working tree master-consistent: move new
   untracked files aside (e.g. to scratch) and revert modified non-test files,
   leaving only the one staged test divergent; then restore everything for the
   Green `--amend`.

**Exempt:** changesets with no product `.py` (docs, spec, work-items, shell,
config) use `chore(...)` / `docs(...)` / `chore(spec):` subjects and skip the
ritual entirely. Always use `mise exec -- git ...` so the hooks fire; never
pass `--no-verify`.

## Progressive guidance (repo-additive)

Repo-specific operational notes live under `.ai/`, loaded on demand rather
than inlined here (livespec core contracts §"Fleet agent-instruction core"
— the progressive-disclosure convention; every reference below MUST
resolve, which `check-agents-ai-references-resolve` enforces).

Both files below existed before this section did, and neither was reachable
from this file — an agent following AGENTS.md as its entry point was never
routed to them. That is the failure mode the resolve check structurally
cannot catch: it verifies that references RESOLVE, so a repo that makes no
references passes with its guidance orphaned.

- Read `.ai/cross-tenant-execution-mirror.md` BEFORE working a work-item
  whose tenant repo differs from the repo that must receive the
  implementation. The Dispatcher sandboxes the `--repo` tenant repo and has
  no per-item repo targeting, so the mirror convention is the only correct
  route; guessing at it is how a change lands in the wrong repo.
- Read `.ai/supervisor-protocol.md` before driving a worker as supervisor —
  the HALT-first preconditions, and the rule that new supervisor handoffs
  are ledger epic entries, never files under `plan/<topic>/`.
- Read `.ai/master-ci-green-preflight.md` BEFORE watching master CI to open a
  dispatch window. The green-master preflight gates on the aggregate job
  `ci-green`, resolved from `dispatcher.master_ci.job`; that name shares no
  prefix with the `check-` family, so an anchored check-run filter assembled
  from the names you remember can EXCLUDE the deciding job and report GREEN
  falsely. The file also records why `gh run list` and the per-commit
  check-runs endpoint can disagree, and that any merge to master re-queues CI
  and closes the window.

## Decision authority — when to ask, proceed, or self-resolve

Fleet-standard guidance, ported from
`livespec/AGENTS.md` §"When to ask, proceed, or self-resolve". The default is
to decide and report, not to escalate.

**This repo already owned half of it.** The fleet's "Drive authorized work to
completion; do not over-ask" rule is maintainer-declared (2026-07-06) and
lives below in "Working with the maintainer (repo-additive)", among the other
maintainer-declared rules. It is deliberately NOT duplicated here — that
grouping is load-bearing, and a second copy would drift from the first. Read
it there; the bullets below are what this repo was missing.

- **A recorded next action is an instruction, not a menu.** When a handoff, a
  work-item, or a plan timeline names exactly one next action, take it.
  Re-presenting it as option 1 of a picker is a documented stall shape: on
  2026-08-20 a track sat roughly sixteen hours doing exactly that, alongside
  five self-decidable engineering calls escalated as standing maintainer
  questions.
- **Research before gating.** If a question is answerable by reading the code,
  the spec, the docs, or by testing on a live system, do that, decide,
  implement, and report for objection. Reserve gates for genuine product or
  values calls, irreversible or outward-facing actions, and secret or
  host-mutation authorization.
- **Only ask on genuine doubt, one thing at a time.** Self-resolve trivial
  wording fixes, internal-consistency repairs, and items clearly aligned with
  established preferences, presenting each with its disposition. When a gate is
  warranted, ask exactly one question per turn.
- **One investigation, one finding, one question.** When a focused
  investigation surfaces unrelated discrepancies, finish the original question
  first and surface only the load-bearing finding; log side observations
  briefly. Cosmetic drift never blocks on its own.
- **Prescribed destructive ops are pre-authorized.** When a destructive git
  operation is the codified mechanism of an adopted workflow — the
  `git commit --amend` of the Red→Green step, for instance — the adoption is
  the authorization. Keep per-instance gating for ad-hoc `--amend`,
  force-push, `reset --hard`, or `branch -D` on unmerged branches.
- **An unratified filter inside a check is conformance, not ratification.**
  Narrowing, excluding, or filtering inside an enforcement check to match what
  the ratified spec already says is a conformance fix — implement it and report
  it. It only becomes a ratification question when the change would make the
  check assert something the spec does not.
- **A question you can answer with a recommendation is a finding, not a
  maintainer question.** If you can state the options, the costs, and which one
  you would pick, you have already done the deciding work. Decide it, record
  the reasoning where the work is tracked, and report it as decided.
- **Disposing a plan child is session-performable.** Closing or re-parenting a
  child that no longer belongs under a plan epic changes where work is TRACKED,
  not what the specification REQUIRES, so it is not a spec-change decision.
  Only a spec-change-tier child routes to `propose-change`; escalating the rest
  deadlocks the archive gate, which refuses while any child sits undisposed.

## Working with the maintainer (repo-additive)

- **Spell out "Definition-of-Ready" in full** — the acronym "DoR" is BANNED
  (maintainer-declared 2026-07-04: non-intuitive, carries no meaning). Never
  use it in any prose, document, work-item, commit, or report; always write
  "Definition-of-Ready". (Quoting pre-existing text verbatim for mechanical
  replacement targeting is the only exception.)
- **Maintainer-facing documents must explain their own notation.** Define
  every symbol before or beside its first use (an arrow, a column, a tally),
  make headings match their content, and write complete sentences over
  compressed fragments.
- **Drive authorized work to completion; do not over-ask** (maintainer-declared
  2026-07-06). When the maintainer names a goal and says to finish or continue
  it ("get this entire track finished", "continue", "don't hold it"), execute
  the WHOLE arc — implement, dispatch, merge, iterate, archive — without pausing
  to confirm each already-authorized step. Ask ONLY for input the maintainer
  alone can give: irreversible/destructive actions, or genuinely ambiguous
  requirements that cannot be settled from the code, spec, or context. An
  operator-flow step that says "present options and let the user select" is
  satisfied by a standing directive once the goal is named — do not re-prompt.
  Surface real blockers and true judgment calls; drop routine "should I
  proceed?" confirmations. Default to acting, then reporting outcomes.
- **Export, then reap: a dead factory run may be removed without a
  per-instance ask** (maintainer-declared 2026-08-26). For any DEAD factory
  run, capture its full record — the `ps -a` row, run id, terminal state and
  blocked reason, completed nodes, node visits and retries, checkpoint sha,
  review verdict, sandbox image and container id, the verbatim failure cause,
  and every dispatch-journal row for the item — into a durable ledger comment
  on the work-item, VERIFY IT BY READ-BACK, and only then run
  `fabro rm --force`. The export is the precondition, not a courtesy: it is
  what converts an irreversible destruction on shared infrastructure into a
  safe one, so a reap whose export has not been read-back verified is not
  covered by this rule. **Read the comment back through `bd comments <id>
  --json` and index `text`, never `body`** — `bd show --json` carries no
  comments at all, so the obvious verification reports the write as lost when
  it succeeded (both traps are catalogued above).
  **Scope this narrowly.** It authorizes exactly one class — removing a run
  that is already dead, after a verified export. It is NOT standing
  authorization for destructive acts generally, and it does not extend to
  reaping a LIVE run, deleting branches or worktrees another thread owns, or
  any other irreversible shared-infrastructure action; those still take a
  per-instance decision from the maintainer. Note also what the reap costs:
  everything reachable only through `fabro inspect` / `dump` / `attach`
  against that run id — the sandbox filesystem included — is gone, so a run
  holding UNPUBLISHED work is not a candidate until that work is recovered or
  written off. Establish publication against the forge and the remote first;
  per the trap catalogue a run's own claim of non-publication has proven
  false. (Context: two orphaned runs on shared `hp` — one blocked at `pr`
  after its work had already merged, one dead at `implement` on the
  compaction-404 defect — each held a scheduler slot while a per-instance
  round-trip was made for permission that the export had already made safe.)
- **Revert decisively; do not diagnose first** (maintainer-declared
  2026-07-11). When something erroneously landed and the corrective action is
  already unambiguous (a throwaway/mistaken change on `master` that must be
  undone), execute the revert/undo IMMEDIATELY — do NOT first spend cycles
  investigating whether it is "really" broken or why. Diagnosis is warranted
  BEFORE acting only when it changes WHAT you do; when you already know the
  action, do it first (worktree → revert PR → merge) and diagnose only if it
  serves a follow-up. (Context: a throwaway proof dispatch auto-merged to
  `master` and a post-merge janitor reported a red check; the revert was the
  correct action regardless of the check result, so pausing to diagnose the
  red was wasted ceremony.)
- **Prefer factory dispatch for factory-safe work; do not default to
  hand-building it** (maintainer-declared 2026-07-15). When a work-item is
  factory-safe (in-repo, dispatchable Python/config — NOT outward-facing upstream
  fabro work), default to running it THROUGH the dark factory
  (`dispatcher.py dispatch --item <id>`), not implementing it in-session. Do NOT
  present the factory path as the heavier or less-preferred option — dogfooding the
  factory is the point ("we should be running things to the factory whenever we
  can"). The "it needs a Codex credential" objection is usually hollow: check
  `~/.fabro/bin/fabro ps` for an in-flight dispatch first; a running dispatch is
  live proof the credential works. The dispatcher self-wraps for credentials but
  often cannot reach the credstore alone — run it already inside
  `with-<project>-env.sh`. Hand-build only when the work is genuinely NOT
  factory-safe (outward-facing upstream fabro PRs, e.g. the codex-factory-telemetry
  O-track) or the maintainer explicitly asks. (Context: after re-planning the
  telemetry emitter, the factory-safe slice F1 was first offered as "hand-build
  (recommended) vs dispatch (heavier)"; the maintainer corrected that the
  factory-safe slice is exactly what should be dispatched.)
- **Master-red restoration is the factory-dispatch exception**
  (maintainer-declared 2026-08-20). If latest master is red and the parked item is
  explicitly the fix for that master health failure, do not try to bypass or
  weaken the green-master gate. Pull the item in-session and deliver it through
  worktree -> PR -> merge; PR CI is independent of master, so the PR can prove the
  fix while the dispatch gate stays fail-closed. `gh run rerun --failed` is not a
  remedy for repeat-flakes: it may be useful evidence, but repeated reruns can
  still leave master red and the fix factory-parked. If red master also makes the
  local pre-commit hook refuse every commit, use the server-side GitHub revert
  break-glass path rather than `--no-verify`: fetch the offending PR's node id
  with a `repository.pullRequest(number:)` GraphQL query, then call
  `revertPullRequest` with that id, passing the query and mutation body from
  files. Prefer re-landing the reverted change paired with whatever it broke in
  one PR, not re-landing it alone.
- **Name the OWNING SESSION when attributing work to another session**
  (maintainer-declared 2026-07-26). When you report that another session made a
  change — a dirty file, a live branch, an in-flight PR, a concurrent worktree —
  identify it by its **session name** (its `/rename` value), not merely by
  project directory or session UUID. The maintainer runs many concurrent
  sessions across the family and coordinates them BY NAME (the names are the
  tmux window names), so "a session in `livespec-console-beads-fabro`" is not
  actionable — it does not say which window to look at. Establish the name
  BEFORE asking any question whose answer depends on what that session is
  doing. Recover it by grepping the session transcript
  (`~/.claude/projects/<project-slug>/<session-id>.jsonl`) for
  `Session renamed to:` — a `type: system` / `subtype: local_command` record
  carrying the `/rename` args — and report it as `<session-name>` (project
  `<project>`, session `<uuid>`), leading with the name. (Context: a revise
  pass blocked on a stale-branch precondition tripped by another session's
  live branch; the options were presented without naming the owner, and the
  maintainer's reply was simply "you need to tell me the name of the session
  which is making this change." Naming it also resolved the block — that
  session's own transcript showed it had already merged the branch and had no
  intent to revise.)
- **Verify every changed path belongs to YOUR thread before you push**
  (maintainer-declared 2026-07-28). Run
  `mise exec -- git diff --name-only origin/master...<your-branch>` as a
  standing pre-push step — every time, not only when you suspect a problem —
  and confirm each path is one the thread you are working owns. Several
  sessions commit to `master` concurrently here, and each
  `plan/<topic>/handoff.md` is owned by its own thread, so "I only meant to
  edit ours" is not evidence. **If you believe your version of another
  thread's file says something theirs does not, do NOT resolve it by editing
  their file.** Drop it from your branch
  (`mise exec -- git checkout origin/master -- <path>`, then
  `--amend`), keep your own thread's edits, and report the difference to the
  maintainer to route to that thread — naming the owning session per the rule
  above. The maintainer's framing: "their thread's record is theirs to write,
  exactly as ours is ours" — the same principle as "never touch another
  session's worktrees or branches", one level up. (Context: a
  `plan/factory-hardening/` branch also carried that thread's
  `handoff.md` — now `plan/archive/dispatch-claim-liveness/handoff.md` — while
  it had PR #1098 open performing the same discharge edit; the collision was
  caught by the maintainer, not by the pushing session.)
- **Vet an escalation before spending the maintainer's attention on it**
  (maintainer-declared 2026-07-30). Before asking the maintainer a question,
  submit it to BOTH an Opus sub-agent and a Codex sub-agent and see whether they
  agree it is worth the maintainer's attention — or whether they can agree on an
  answer between themselves. Escalate only if that vetting supports it. **Why:**
  this is the operational teeth on "drive authorized work to completion; do not
  over-ask" above. It converts a judgment call about interrupting into a cheap,
  checkable procedure instead of leaving it to one agent's self-calibration.
  **How to apply:** spawn both vetters in ONE message so they run concurrently;
  give each the SAME tightly-framed brief — the verified facts, the concrete
  options with their costs, and the standing rules that bear on it; require a
  YES/NO first word plus an explicit "no fourth option" rather than an invented
  one; have them answer independently, and tell them a genuine split is more
  useful than agreement. Keep driving the conforming default while they run —
  vetting is never a reason to idle. This authorizes the Agent tool for THAT
  purpose specifically; it is not blanket permission to delegate ordinary work.
  - *Worked example, which is what proved the rule.* The
    `retire-host-dispatch-cap` thread's factory dispatch of `bd-ib-vmve.2` was
    refused by the very `host_dispatch_cap` guard it was deleting: two runs from
    OTHER repos held a cap of 2 while eight Fabro scheduler slots sat idle, so
    this repo was refused with zero runs of its own in flight. The candidate
    escalation offered three options — wait for a drain, transiently commit a key
    the spec ratified minutes earlier forbids, or hand-build the deletion against
    the handoff's factory-only mandate. Both vetters independently returned
    NO-do-not-interrupt, take the wait, and no fourth option; both also
    independently confirmed the fail-open prohibition below. The wait was
    correct — capacity freed after 38 minutes and the dispatch went green.
  - *Known limitation: this protocol can silently degrade to one leg.* In this
    harness the Opus sub-agent channel returned THREE empty idle notifications
    before it eventually answered, and the failure mode is the dangerous kind —
    an idle notification carrying NO CONTENT reads as completion rather than as
    failure. A protocol requiring two opinions therefore has a quiet path to
    running on one without announcing it. Treat a missing answer as a MISSING
    ANSWER: count it as absent rather than as assent, say so explicitly, and
    state how many legs actually reported when you cite the vetting. Silence is
    not agreement. A direct follow-up request is worth making before writing a
    leg off — in this instance that is what finally produced the answer.
  - *A fourth option WAS constructed and rejected; do not reinvent it.* The
    strongest candidate was to bump the cap in an UNCOMMITTED `.livespec.jsonc`
    inside a throwaway worktree, which clears the spec's literal "committed
    configuration key" wording. It is rejected: it is the commit-the-key option
    with the evidence removed — the same minutes bought, but leaving no diff a
    reviewer could ever see. Satisfying a rule's letter by making the violation
    invisible is not compliance.
  - *General principle: never defeat a live check to get past it — and note that
    blinding a check is WORSE than the honest violation, not a milder version of
    it.* A gauge that FAILS OPEN when it cannot observe its input is a standing
    temptation: blinding the input (an unresolvable binary, a doctored `PATH`,
    anything that makes the observation fail) converts a refusal into a pass
    instantly. That is worse than openly taking the forbidden option because it
    MANUFACTURES A COUNTERFEIT ENVIRONMENTAL FAULT — the record then reads as a
    genuine incident, so the one artifact a reviewer would use to reconstruct why
    the work proceeded has been falsified. Committing a forbidden key is at least
    legible in a diff; blinding a gauge lies in the journal. This holds even when
    the check is the very thing you are authorized to delete: removing a guard by
    the sanctioned path and evading it by engineering its blind spot are not the
    same act. If a fail-open warning appears on a retry you did not engineer,
    STOP and report it rather than riding the fail-open through. (The instance
    that motivated this — the dispatch admission mutex's `fabro ps` gauge, which
    proceeded "on the capacity-slot gauge alone" when `ps` was unobservable — was
    deleted with that mutex by `bd-ib-vmve.2` in `0eeca13`. The principle is
    recorded because fail-open checks recur, not because that gauge still
    exists.)
- **Never label an option set as numbered tiers or levels; each enumeration
  value names what it IS** (maintainer-declared 2026-08-31). The
  `RepoIntegrationContract` conformance premises are the canonical instance:
  their mode enumeration is `no_op`, `shell_argv`, and
  `internal_livespec_dev_tooling` — never "tier 0/1/2" — and those names are
  used identically in the config discriminator, the dispatch-time warning,
  and every document that describes them. Any option that couples an adopter
  to livespec's internal dev-tooling MUST be labeled, on the surface that
  offers it, as introducing a dependency on livespec internal tooling that is
  UNSUPPORTED and may be unreliable. **Why:** a numbered tier carries no
  meaning to an adopter reading a dispatch warning, while a self-describing
  value tells them what they are choosing; and without the caveat the
  shared-package option reads as the recommended one when it is the one this
  fleet does not support for anyone else. **How to apply:** pick descriptive
  snake_case values for any adopter-facing enum, make the warning text
  enumerate them by name with one line each, and attach the unsupported caveat
  to every `internal_*` option. (Context: the conformance-premise fields were
  first drafted as "tiers"; the maintainer rejected the label and ruled the
  three names and the caveat while landing plan `bd-ib-vblnq2`.)

## Verification discipline (repo-additive)

Five rules. Rules 1-3 come from a 2026-07-28 three-way exchange between the
`dispatch-claim-liveness`, `console-happy-path-mvp` and `factory-hardening`
tracks, in which **three sessions independently reached confident wrong answers
on the same question in one day**; rules 4-5 were added 2026-08-27 by the
`homelab-loop-hardening-orchestrator` thread, each from a near-miss caught by a
control rather than by care. Each bad method produced a **confident wrong
answer rather than an obviously empty one**, which is why none self-announced.
Full account, with every measurement:
`plan/archive/dispatch-claim-liveness/handoff.md` §"THE THREE STANDING RULES".

Provenance, because a rule with a visible author is harder to dismiss:
`console-happy-path-mvp-supervisor` authored Rule 1's form and Rule 3's example;
`factory-hardening-supervisor` contributed Rule 2's sharper variant and caught
the third near-miss.

1. **Asserting an absence requires stating the scope searched.** "No call site",
   "no release", "no occurrence" — say what population you searched, and make it
   the whole workspace unless there is a reason it cannot be. If the check could
   not have returned the other answer, it is not evidence.
   *Worked example:* "no released build carries this fix" came from sampling two
   plugin caches that were **created before the fix commit existed**, so their
   lacking it was guaranteed and carried zero information. When the question is
   "was this released", ask `git tag --contains <sha>`.

2. **Verify the absence of the RIGHT token — a count is not a behavior test.**
   Pick a token that *cannot appear unless the behavior is there*, and say which
   token you chose and why.
   *Worked example:* a fork's `pr.md` was judged to lack a rebase-before-push fix
   because it contained 2 `rebase` mentions against our 6. **Both of its 2 were
   innocent** — a title, and a `gh pr merge --rebase --auto` arm — so six
   mentions in auto-merge context would have reported the fix PRESENT. The
   discriminating token was `fetch`: ours 2, theirs 0. **The count was
   directionally right and still not evidence.**
   - *Corollary — prefer a PROVENANCE question to any content probe.* Before
     grepping a file's contents for a fix, ask whether it *could* contain it:
     that same fork's `pr.md` had exactly ONE commit in its history, 18 days
     older than the fix. `git log -- <file>` has no wrong-answer failure mode.
   - *Corollary — search for a literal COPIED from the artifact*, never one
     reconstructed from memory. Four probes failed this way in one session
     (missing backticks; a line break inside a code block; another repo's
     invocation syntax; a `| head` that truncated the hits). **A verification
     that can only fail silently is not a verification.**

3. **An instruction can outlive the condition that made it correct.** The danger
   is not writing something false — it is writing something **true that stops
   being true while still reading as authoritative**, in the section a successor
   trusts *instead of* checking. A "do not re-derive this" list is the
   highest-risk place in any document for exactly that reason: date such entries
   and re-verify before quoting one.
   *Worked example:* "expect the stale-base refusal, apply the known recovery"
   was true while a worker ran a week-old plugin and false the moment it
   restarted — and it reached a merged handoff either way.

4. **Concurrence is not independence when the method is shared.** Two parties
   applying the same method to the same artifact produce **one** measurement, not
   two. Their agreement shows the method is DETERMINISTIC, not that the answer is
   right — and it is *more* persuasive than a single wrong answer, because the
   receiving party sees N reports and cannot see they share one origin. This is
   the multi-party form of Rule 2's problem; Rule 2 asks whether your instrument
   is pointed correctly, this one asks whether the second opinion is a second
   instrument.
   *Worked example (2026-08-27):* two sessions independently measured a tenant's
   spec-commitment census by reading the projection's bridged
   `spec_commitment_hint` while reasoning about a guard that reads the
   beads-native `spec_id` column, and the concurrence was relayed onward as
   corroboration. It was one reading taken twice. Re-taken against **both**
   fields it happened to hold — but a divergence could not have printed under the
   original method.
   *The larger instance, same day:* a coordinator PRESCRIBED one reading method
   to four peers and read their agreement as fourfold confirmation. Two defects
   existed in the prescription, and both were caught only because two peers
   **departed** from the brief. Compliance would have banked three greens on a
   holed method.
   - *Corollary for anyone standardising a method:* a departure from your brief
     is **signal**, not noise to be corrected back into line. It is the only
     thing that can falsify the brief itself.
   - *What a genuine second reading looks like:* a different artifact, not the
     same one read again. Another tenant found a free-form value that the first
     tenant's data structurally could not contain — that is corroboration in the
     sense the shared-method census was not.

5. **A next-action line EXECUTES — author it from evidence, not from status.**
   Under an unattended resume (`LIVESPEC_PLAN_UNATTENDED`), `resume_directive`
   returns `ask: False` whenever the newest plan handoff names exactly one next
   action, and the session **takes it directly** — no picker, no human. A
   next-action line is therefore not advice to a successor; it is an instruction
   that fires.
   *Worked example (2026-08-27, this repo, caught before dispatch):* a handoff
   named "Dispatch `bd-ib-6mnyq4`", authored from the item's STATUS — `ready`,
   already admitted, no dependency edge, factory idle. The item carried a binding
   rider, "DISPATCH HELD, DELIBERATELY, PENDING `bd-ib-u7nrue`", whose release
   condition was that sibling's PR merging; it had not merged. Both items insert
   into the same pre-dispatch sequence in `_dispatcher_run_checks.py`, which is
   why the hold exists. The directive resolved `ask: False`, so an unattended
   resume would have dispatched straight into the collision the rider was written
   to prevent.
   **Before writing any item id into a next-action line, run
   `bd comments <id> --json` and read it.** Status is not evidence that an item is
   dispatchable: riders arrive AFTER filing, they are binding scope, and neither
   the description nor `acceptance_criteria` announces that any exist — this is
   the "read its comments" rule above, promoted from a pre-implementation check to
   a pre-*authoring* one, because the automatic path reaches dispatch without a
   human ever re-reading the item.

**Run these on your own work, not only on other people's.** Every instance above
was caught by a second signal disagreeing, never by the check announcing itself.
Passing a check you never ran is luck, not method.
