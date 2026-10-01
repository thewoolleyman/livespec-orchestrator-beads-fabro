# Proof-asset inline-rendering measurement (2026-10-01)

Work-item: `bd-ib-b4u6b7` (S5 — `publish_draft` and `proof_capture`, the proof
asset store and the record format). Plan epic: `bd-ib-7sjdzv`.

## What had to be measured, and why

`SPECIFICATION/contracts.md`'s Proof-of-Done-record clause states ONE
requirement a proof asset store must satisfy:

> a viewer authorized on the repository sees each image inline in the record
> comment, and no unauthorized viewer can fetch it

and then requires that "the implementing slice MUST measure the requirement on a
private repository before selecting a store". Where the first half cannot be met,
the record carries one authenticated link per image instead, the inline half is
waived for that repository, and the waiver is journaled naming the store measured.

So this is not a design preference to be argued. It is a question about live
forge behaviour, and the slice is not allowed to select a store without asking it.

## Method, and the controls

Measured against live GitHub on 2026-10-01 from inside the dispatched Fabro
sandbox, **read-only throughout** — no release was created, no asset uploaded,
and no unrelated repository was mutated.

The forge renders an inline image in a comment by fetching the referenced URL
through its own **anonymous** image proxy. Anonymous fetchability of
repository-origin content is therefore a NECESSARY condition for inline
rendering. That is what was probed.

| # | Probe | Expected if the policy is right | Measured |
|---|---|---|---|
| A | Anonymous `GET` of a PRIVATE repository's own-origin content — `github.com/thewoolleyman/window-namer/raw/HEAD/README.md` | not 200 | **404** |
| A′ | Same, via `raw.githubusercontent.com` | not 200 | **404** |
| B | Anonymous `GET` of a PUBLIC repository's own-origin content — this repository's `README.md`, both hosts | 200 | **200** (both) |
| C | Authenticated read of the same private repository (`gh api repos/thewoolleyman/window-namer`) | readable, `private` | **readable, `private`** |

Probe B is the control that matters most: it establishes the instrument **could
return the other answer**. Without it, the two 404s in A are equally consistent
with "private content is not anonymously fetchable" and with "this sandbox has no
egress at all" — and nothing in the output distinguishes those. Probe C is the
second control, establishing the instrument was **aimed at** a repository that
exists and is genuinely private, rather than at a typo that 404s for the dull
reason.

## Conclusion

On a **private** repository, release assets are served from the same
authenticated origin as every other private artifact, and an anonymous fetch does
not reach it. The forge's anonymous image proxy therefore cannot fetch it, so an
inline reference cannot render. **The inline half is not satisfiable for a private
repository by the release-assets store**, and the authenticated-link fallback
applies. The second half of the requirement — no unauthorized viewer can fetch it
— **is** satisfied, which is why the store is still selectable there.

On a **public** repository the anonymous fetch succeeds, so the inline reference
renders; and the asset's audience equals the repository's own audience, so the
second half is satisfied vacuously rather than violated.

Implemented as `proof_rendering_for_visibility` in
`commands/_dispatcher_proof_release.py`: `public` → `inline`, everything else →
`authenticated_link`. The resolution is journaled per repository under the
`proof-asset-store` dispatch-journal stage, naming the store measured
(`release_assets`), the visibility read, the rendering selected, and
`inline_waived`.

## What this measurement did NOT establish

Stated explicitly, because a later reader will otherwise assume it did.

**No private repository reachable from this sandbox carried a release.** Checked
five (`window-namer`, `gastown-vps`, `cwoolley-gitlab`,
`elite-context-engineering`, `scorecard-code`); every one reported zero releases.
So the probe was aimed at private **own-origin content**, not at a private
**release asset URL** specifically. The inference from the first to the second is
that both are served from the same authenticated origin — which is sound, but it
is an inference and not a measurement.

Creating a release on an unrelated private repository to close that gap was
deliberately NOT done: it is an outward-facing mutation of a repository this
work-item does not own, and the fallback it would potentially narrow is the
conservative direction anyway.

**Follow-up for whoever provisions the first private-repository prerelease:**
re-probe the asset `browser_download_url` directly. If it renders inline after
all, narrow `proof_rendering_for_visibility`. The cost of the current answer being
too conservative is one inline rendering; the cost of it being too permissive
would be a reference that leaks. The asymmetry is why the fallback is where it is.

## Residual: the measured rendering does not yet reach the sandbox

The gate measures and journals the rendering per repository, but the sandbox
currently receives only two of the three projected keys —
`LIVESPEC_PUBLISH_BRANCH` and `LIVESPEC_PROOF_ASSETS_RELEASE_TAG`. The third,
`LIVESPEC_PROOF_ASSET_RENDERING`, is not projected, and `proof-capture.md`
therefore falls back to the authenticated-link form.

The blocker is mechanical rather than a design question:
`commands/_dispatcher_loop.py` sits at **LLOC 250**, exactly the hard ceiling the
`file_lloc` gate enforces, so the one call site that could thread the resolution
into the run-config overlay cannot take another argument until that module is
decomposed along a cohesion seam. The overlay projection was deliberately kept
**pure** instead — an earlier draft probed the forge from inside it and spawned a
real `gh` in 104 otherwise sealed tests, which is not a projection that belongs on
a path every dispatch materializes offline.

The fallback is the same fail-safe direction `proof_rendering_for_visibility`
takes for an unmeasured repository, so the residual costs an inline rendering on
public repositories and can never publish a leaking reference. Closing it is a
pure plumbing change behind a `_dispatcher_loop` decomposition.
