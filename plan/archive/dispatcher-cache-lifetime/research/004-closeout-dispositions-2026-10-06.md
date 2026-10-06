# Independent closeout findings and dispositions, 2026-10-06

The independent native reviewer (Claude session
`688be897-d381-449b-9287-56908574c61c`) verified the released v0.173.6 host
behavior and then returned NOT COMPLETE on three administrative residuals.
That first report is retained verbatim in the epic's completeness evidence;
the corrections below do not retroactively change its verdict or any original
TDD chronology.

## Credential incident follow-up

Standalone **bd-ib-ffyiuc** carries the credential owner's rotate-or-no-rotate
decision and any authorized remediation for the 2026-10-06 transcript
exposures. It includes the cache-lifetime factory/coordinator incidents and
the later main Herdr audit incident recorded on overseer-uzvcbn at 19:38:32Z.
No values are included. Normal intake routed this human-only owner decision to
blocked; it is not factory implementation or authorization to rotate shared
credentials. The named carrier, rather than this completed payload plan,
owns that residual decision. Containment does not revoke exposed credentials.

## Original git objects are preserved in durable private bundles

Research 002 and 003 describe recovery refs inside the original factory
repository. Those refs were not all imported into the primary clone or
published on origin. Their present-tense preservation wording must not be
read as a claim that an arbitrary checkout contains those objects.

The coordinator originally exported the actual objects into private `/tmp`
bundles. The independent reviewer correctly found that `/tmp` is tmpfs on
this host. All thirteen bundles have now been copied byte-for-byte, with
SHA-256 and head inventories verified, to persistent ext4 storage:

`/home/ubuntu/.local/state/livespec-evidence/dispatcher-cache-lifetime-20261006/`

The directory is mode 0700, bundles and `inventory.json` are mode 0600.
The inventory SHA-256 is
`fa0011f43371dfa23119b5467e8c4ac94ad1ac338788affc237cec949da8e351`.
These are host-private recovery artifacts, not portable public proof assets
or a promise of an off-host backup.

The complete through-cycle-15 bundle is
`dispatcher-cache-lifetime-recovery-through-cycle15.bundle`, SHA-256
`a4d267025ad50a54279efe1a0e35b2746fbaaf22e208c297882d44d413a8dd76`.
Its recorded heads include the actual original `4ffae66e` Red, replacement
objects, recovered `9fb4bce6` Green, and the cycle-9/10 incident objects.
The separate `a5-original-red.bundle`, SHA-256
`6af6a30399054dc60dc20859eb8f21b9eb01620761b066ded67c6c57b6d3fefa`,
preserves the actual accepted `c6f59fb1` Red object.

Inspect with `git bundle list-heads`; import into a separate audit clone if
object-level replay is needed. Do not rewrite the merged history or recreate
old Red objects. The old branch-specific verifier is not a master acceptance
test: its unpublished-branch premise is false after merge, and its object
checks require the preserved original object store. Master retains the
landed trailers and frozen files; those alone do not turn the disclosed
cycle-9/10 late baseline replays into original Red-first evidence.

## Existing wrapper diagnostic carrier

**bd-ib-ewcj**, Defect 1, is the named live carrier for the credential-wrapper
stderr-discard mechanism described in research 003. A new comment on that
item records the actual 2026-10-06 minimum-release refusal instance and links
back to this plan. The old phrase "left as a filed finding" meant an already
existing mechanism but omitted its identifier; this note supplies it.
No wrapper diagnostic product repair is included in this archive.

The generic notification-title observation is pre-existing and outside the
declared work; it was an optional reviewer suggestion, not an unfulfilled
payload requirement. The proof-prompt contradiction remains recorded on
bd-ib-7sjdzv; Herdr work remains with overseer-uzvcbn; currency remains with
bd-ib-3ftj. The original incident disclosures and proof limitations remain
unchanged.
