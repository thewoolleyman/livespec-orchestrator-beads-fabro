# Beads ledger traps: connection, wrapper, listing, comments and metadata

Moved word for word from `AGENTS.md` §"Beads runtime prerequisites" on 2026-10-30, when the maintainer
directed AGENTS.md split into a short core plus read-on-demand `.ai/` files
(answer recorded on `livespec-dev-tooling-dfixhe`; plan epic `bd-ib-raqyki`).
Words such as "above" and "below" point into the AGENTS.md this text came from;
the sections they name now live in the `.ai/` files AGENTS.md routes to.

**Run beads commands from the target repo root.** Per-command `bd` resolves its
connection from the current directory's `.beads/config.yaml` (auto-discovery),
NOT from any resolved config object — so run from the intended repo's root, or
`bd` silently operates on the wrong tenant.

**An "Access denied" / "no beads database found" failure almost always means you
are running OUTSIDE the wrapper** (the bare `BEADS_DOLT_PASSWORD` is absent), not
that a secret is missing. Re-run under your project's configured env wrapper
(`with-<project>-env.sh`) -- `<command>`. Never hand-hunt the secret or reach
around the seam with raw `mysql` / `dolt` / `sudo`.

**But when EVERY tenant refuses at once while you ARE under the wrapper, the
wrapper's own 300-second cache is poisoned — not 1Password, not the credstore,
not Dolt.** Discriminate it in one line, probe-only:
`with-livespec-env.sh -- sh -c 'printenv BEADS_DOLT_PASSWORD | wc -c'` printing
`0` while `OP_ENV_WRAPPER_CACHE_TTL=0 with-livespec-env.sh -- sh -c '...'`
prints the normal length in the same minute. Measured 2026-10-01 01:03–01:10
on this host: `bd` returned `Error 1045 Access denied` for both this tenant and
`livespec-dev-tooling`, the default path injected zero bytes, the cache-bypass
form injected 29, sibling wrappers (`with-openbrain-env.sh`, `with-homelab-env.sh`)
were unaffected, and the default path healed itself at 01:10 with nothing
changed. Mechanism (from the rendered wrapper): on a cache miss it stores the
DIFF between the caller's environment and what `op run` injected, in the
invoker's kernel persistent keyring, and replays that diff to every caller
until the key's timeout; a NESTED caller — a process already running under the
wrapper that re-invokes it for `bd` or `gh`, which every long-running `drive`
dispatch does from its janitor — already holds the secrets, so its diff is
nearly empty, and for the next five minutes everyone else gets nothing. Filed
upstream as `thewoolleyman/1password-env-wrapper` issue #17 with the suggested
fix; expect recurrence while any wrapped dispatch is alive on the host until it
lands. Do NOT touch the keyring, do NOT hunt the secret, and do NOT flip any
credential configuration: the entry expires on its own, and the TTL=0 form is
the wrapper's documented per-call knob, useful as the DISCRIMINATOR, not as a
standing bypass. Note also the instrument-aim trap inside this trap: the cache
lives in the INVOKER's persistent keyring (uid 1000 — the wrapper drops
privileges before stage 2), so inspecting root's keyring reports "empty" with
perfect confidence about the wrong population.

**`[ERROR] <timestamp> (500) Internal Server Error: Server experienced a fatal
error.` from a wrapped `bd` call comes from the WRAPPER's 1Password call, not
from Dolt — `bd` never ran.** The wrapper calls the 1Password CLI to fetch the
credential before `bd` starts. When the 1Password service answers HTTP 500,
the wrapper fails. The string is compiled into the 1Password CLI
(`strings /usr/local/bin/op` contains it), while a Dolt failure reads
`Error NNNN (SQLSTATE)`. Remedy: check whether the write landed (read it back,
with stderr kept separate), retry once, and do not diagnose the server.
Measured 2026-10-16 at 23:02:07Z and 23:10:31Z on two `bd comment` writes to
the `livespec-dev-tooling` tenant. Neither landed, an immediate retry of each
succeeded, reads kept working (the wrapper serves most calls from its cache),
and `doltdb.service` logged no error, fatal or panic in either window. If it
recurs often, route it to the 1password-env-wrapper owner (retry with backoff
when `op` returns a 5xx). It is distinct from the cache-poisoning signature
above, which injects an EMPTY password and so surfaces as a Dolt `Error 1045`.

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
