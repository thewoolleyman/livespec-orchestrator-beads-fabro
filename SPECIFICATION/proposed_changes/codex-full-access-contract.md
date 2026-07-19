---
topic: codex-full-access-contract
author: claude-fable-5
created_at: 2026-07-18T00:00:00Z
amended_at: 2026-07-19T00:00:00Z
---

## Proposal: Manifest-gated Codex full-access contract

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Ratify the permanent Codex full-access contract for the Beads/Fabro
orchestrator. When the current repository is a livespec fleet member or an
official adopter listed by the fleet manifest, the orchestrator MUST enable
Codex's `danger-full-access` posture for the Codex surfaces it relies on:
the Codex companion plugin's interactive review/rescue paths and the
orchestrator-owned `codex exec` credential-refresh path. Repositories outside
that manifest remain default-off unless they explicitly opt in locally.

The mechanism is intentionally manifest-gated, not global. It gives the
maintainer's own fleet and official adopters the full-access execution required
for honest tests, `git`, `gh`, and networked review, while avoiding a silent
full-access posture for unrelated external users who happen to install the
plugin.

**Amendment note (2026-07-19).** This proposal was authored 2026-07-18, BEFORE
the implementation landed. The contract has since shipped in full (S1 #782,
S2 #791, S3 #800, C1 #803) along with three defect fixes (#793, #795) and the
fail-closed hardening (`eeb80fe`, `8283d5e`). The normative text below has been
corrected to describe the system AS BUILT AND VERIFIED. Ratifying the original
wording would have created a false conformance signal — and in one case
(the canary's deciding signal) would have re-authorized the exact defect #795
fixed. Each correction is marked and justified.

### Motivation

The shipped repo-local fix documented in `plan/codex-yolo-sandbox/handoff.md`
proves the root cause and the working posture: Codex companion review/rescue
threads default to restrictive sandbox modes, ignoring the host's raw
`codex exec` configuration, so adversarial review can appear to run while being
unable to execute the checks it is asked to perform. The permanent design in
`plan/codex-yolo-sandbox/permanent-fix-design.md` resolves the scope issue:
the fix must travel through this orchestrator plugin's distribution for fleet
members and official adopters, and it must be gated by fleet membership or local
opt-in.

This belongs in `constraints.md` because, like the Fabro pin, it governs an
external runtime the plugin does not own. The constraint must name the deciding
signals and verification commands so review can distinguish a conformant
full-access posture from a silently re-sandboxed one.

### Proposed Changes

**(1) Add a new `constraints.md` H2 section immediately after
§"Fabro runtime constraints".**

ADD:

```markdown
## Codex full-access runtime constraints

Codex is an EXTERNAL agent runtime: the plugin does not vendor Codex, does not
own OpenAI's Codex companion plugin, and does not own Codex's host-wide
configuration. **Scope — "the Codex factory surfaces"** means the surfaces this
orchestrator depends on for factory operation: the Codex companion plugin's
interactive review/rescue paths (`codex:codex-rescue`, `/codex:review`,
`/codex:adversarial-review`) and the orchestrator-owned raw `codex exec`
credential-refresh invocation. These constraints govern when those surfaces MUST
run with Codex `danger-full-access`.

- **Gate evaluation is local and hook-time.** Codex full access is decided at
  hook time (SessionStart, and the raw `codex exec` credential-refresh command)
  SOLELY from an explicit local opt-in signal (`LIVESPEC_CODEX_FULL_ACCESS`,
  which MUST override in both directions) or a committed local membership marker
  (`.livespec.jsonc`'s `codex_full_access.fleet_listed`). Hook-time evaluation
  MUST NOT shell out to `git` or read the fleet manifest directly, so that
  SessionStart stays fast and cannot stall a session on a subprocess.
- **Marker provenance.** That marker MUST be derived from the livespec core
  fleet manifest (`.livespec-fleet-manifest.jsonc`) rather than hand-maintained,
  via a distributed `refresh` operation that resolves the repository identity
  from `git remote get-url origin` and evaluates fleet-member or official-adopter
  membership through the same fleet-contract machinery. For every repository not
  so listed, Codex full access MUST default OFF. Installing the plugin alone MUST
  NOT silently put an unrelated external repository into a full-access Codex
  posture.
- **Fail closed on authorization.** If the gate mechanism itself cannot be loaded
  or evaluated, every surface it governs MUST default to full access being OFF.
  This is distinct from — and MUST NOT be confused with — the operational
  fail-open posture required of the hooks themselves: a SessionStart hook MUST
  NOT raise or crash on a malformed, unreadable, or unwritable input, because a
  hook that fails hard can wedge every session. Fail OPEN on operation; fail
  CLOSED on authorization.
- **Companion-plugin surface.** When the gate is ON, the orchestrator-distributed
  hook MUST make the active Codex companion thread-parameter chokepoint resolve
  to `danger-full-access`, while preserving an explicit per-run downgrade escape
  hatch (`CODEX_COMPANION_SANDBOX`, e.g. `read-only` or `workspace-write`).
  Because this rewrites a third-party plugin cache that may change shape, the
  same distribution MUST include a canary that classifies the active companion
  source as `stock`, `patched`, or `drift` by matching the FULL exact full-access
  rewrite expression. A loose substring or bare env-var-name match is
  INSUFFICIENT and MUST NOT be used: an unrelated upstream file can mention the
  same name without carrying the patch, which would falsely classify as patched
  and silence the canary. When the gate is ON and the source classifies as
  `drift` — neither the stock default nor the exact patched expression present —
  the canary MUST emit a loud operator-visible warning rather than silently
  treating the sandbox posture as unknown.
- **Raw `codex exec` surface.** When the gate is ON, the orchestrator-owned raw
  `codex exec` credential-refresh invocation MUST run in full-access mode via
  `--dangerously-bypass-approvals-and-sandbox`. Every orchestrator-owned raw
  `codex exec` invocation MUST redirect stdin from a source that reaches EOF
  (`< /dev/null`, or an equivalent `DEVNULL` in an argv-form spawn), because
  `codex exec` reads additional prompt text from stdin until EOF even when a
  prompt argument is present, and an inherited open socket therefore stalls the
  process indefinitely before it does any work.
- **Out of scope — operator dogfooding.** Manually-typed
  `codex exec <plugin>:<op>` dogfooding commands are NOT gated by this contract.
  Their posture comes from the operator's own host-wide `~/.codex/config.toml`,
  which has no per-repository awareness. That host configuration is a
  maintainer-owned host setting, not something this plugin installs or manages,
  so it is outside the manifest gate. This exclusion is stated explicitly so the
  gate's promise is not read more broadly than it holds.
- **Verification.** The companion-plugin rule is decided by the canary's
  classification of the active Codex companion source against the exact
  full-access rewrite expression. The raw `codex exec` rule is decided by the
  actual rendered argv for orchestrator-owned invocations, including the
  full-access flag and the stdin EOF redirect. Marker provenance is decided by
  re-running the `refresh` operation against the current manifest and diffing the
  resulting marker: any difference means the committed marker has drifted from
  the manifest it claims to derive from. Review-time verification MUST check
  those deciding signals whenever the hook, canary, gate, Codex invocation
  wrapper, or Codex dogfooding instructions change.
```

Rationale for the new H2 instead of adding bullets to §"Skill orchestration
constraints": the contract is not about skill prose ownership. It is an
external-runtime posture constraint, parallel to §"Fabro runtime constraints",
and it must keep the deciding commands/signals visible at review time.

*Amendments to this section vs. the 2026-07-18 draft, and why:*

- *Gate evaluation / marker provenance split.* The draft said the gate keys on
  `owner/repo` "resolved from `git remote get-url origin`", with a local marker
  that "MAY cache that decision". That inverts the shipped design: `gate_state`
  never resolves identity or reads the manifest — it reads the env override and
  the committed marker, and manifest resolution lives only in the separate
  `refresh` path. Ratifying the draft would have required behavior that does not
  exist, and would have made the gate slow and subprocess-dependent at
  SessionStart.
- *Canary deciding signal.* The draft required a check that the source "contains
  the expected `danger-full-access` sentinel". That loose match WAS the defect
  fixed in #795 — an upstream file merely mentioning `CODEX_COMPANION_SANDBOX`
  classified as patched and silenced the canary, and the unmerged upstream
  toggle proposal is named `CODEX_COMPANION_SANDBOX_MODE`, which contains that
  name as a substring. The amended text requires the full exact expression and
  explicitly forbids the substring form.
- *Fail-closed bullet added.* The `eeb80fe` / `8283d5e` hardening post-dates the
  draft. The draft's "rather than failing open silently" also conflated two
  different axes; the amendment separates operation from authorization.
- *Raw-exec scope narrowed + dogfooding exclusion added.* The draft required
  full access for "every orchestrator-owned raw `codex exec` invocation... or
  through an equivalent host-wide Codex configuration", which contradicted its
  own manifest-gate promise: the host-wide config grants full access to every
  repo on the host regardless of manifest listing. The gate is in fact consulted
  at exactly one call site (credential refresh), so the amendment scopes the
  requirement there and names the dogfooding path as explicitly out of scope.
- *Verification bullet* now names a decidable command for marker provenance,
  which the draft asserted without any way to check.

**(2) Reconcile Scenario 21 so the Codex plugin scenario covers both discovery
and full-access posture.**

REPLACE the H2:

```markdown
## Scenario 21 — Codex skills picker discovers drive by short name
```

WITH:

```markdown
## Scenario 21 — Codex plugin discovery and full-access posture
```

REPLACE the Scenario 21 feature block with:

```gherkin
Feature: Codex plugin discovery and full-access posture
  As an operator using the Codex TUI and Codex-backed factory review
  I want the orchestrator's Codex plugin to be discoverable and full-access only
    under the manifest-gated contract
  So that official fleet/adopter repos get honest executable review without
    silently changing unrelated external repos

Scenario: The /skills picker renders drive under this plugin
  Given the livespec-orchestrator-beads-fabro Codex plugin is installed
  And the operator opens the Codex TUI
  When the operator opens "/skills"
  And chooses "List skills"
  And searches for "drive"
  Then the picker renders "drive (livespec-orchestrator-beads-fabro)"
  And the rendered row is typed as a Skill
  And the operator does not need to search for the colon-qualified
    "livespec-orchestrator-beads-fabro:drive" form

Scenario: A fleet-listed repository gets Codex full access
  Given the repository's committed "codex_full_access.fleet_listed" marker is
    true, previously derived from the livespec core fleet manifest by the
    "refresh" operation
  And no local opt-out is set
  When the orchestrator's Codex full-access gate is evaluated
  Then the companion-plugin review/rescue chokepoint is rewritten to
    "danger-full-access"
  And the canary classifies the active companion source by matching the exact
    full-access rewrite expression
  And the orchestrator-owned raw "codex exec" credential-refresh command runs
    with the full-access flag and stdin redirected from an EOF-reaching source

Scenario: An unrelated external repository remains default-off
  Given the repository has no committed fleet-listed marker
  And no local Codex full-access opt-in is set
  When the orchestrator's Codex full-access gate is evaluated
  Then the companion-plugin chokepoint is not rewritten by this plugin
  And the orchestrator-owned raw "codex exec" credential-refresh command does
    not infer full access from plugin installation alone

Scenario: A gate that cannot be evaluated denies full access
  Given the gate mechanism cannot be loaded or evaluated
  When a surface governed by the gate is invoked
  Then that surface runs WITHOUT full access
  And the failure does not crash the invoking hook or command
```

This keeps the existing picker assertion intact while adding the posture
contract Scenario 21 now needs to carry. The heading still refers to the
orchestrator's Codex plugin, matching the design note that Scenario 21 is the
existing Codex behavior anchor.

*Amendment: the draft's second scenario opened with "Given the current
repository identity appears in the livespec core fleet manifest ... When the
gate is evaluated". As written that Given is UNVERIFIABLE, because evaluating
the gate never consults the manifest — only a prior `refresh` does. The Given
now names the committed marker, which is what the gate actually reads. A fourth
scenario was added for the fail-closed-on-authorization behavior.*

**(3) Update `tests/heading-coverage.json` in the revise pass.**

ADD a heading-coverage entry for the new constraints heading:

```json
{
  "heading": "## Codex full-access runtime constraints",
  "spec_root": "SPECIFICATION",
  "spec_file": "constraints.md",
  "test": "TODO",
  "reason": "External-runtime posture constraint over Codex and the OpenAI Codex companion plugin: the deciding signals are the local opt-in/marker gate, the canary's exact-expression classification of the active companion source, the fail-closed-on-authorization default, and the rendered raw codex exec full-access/EOF behavior. Unit coverage for the gate and canary exists under tests/hooks and tests/hooks_plugin; a single bindable test ID for the whole constraint awaits an integration-tier test that exercises the gate and canary end to end."
}
```

For the renamed Scenario 21 entry, UPDATE ONLY the `heading` text to
`## Scenario 21 — Codex plugin discovery and full-access posture`, and
**PRESERVE its existing `test` value**
(`tests.e2e-cli.test_codex_skill_picker.test_skills_picker_finds_drive_by_short_name`)
— that test exists at `tests/e2e-cli/test_codex_skill_picker.py` and still
covers the picker-discovery half of the merged scenario. Extend its `reason` to
record that the added posture sub-scenarios are not yet bound to that test.

*Amendment: the draft said to "leave its `test` as `TODO`". The entry is NOT
`TODO` today — it carries a real bound test — so following the draft verbatim
would have silently deleted real coverage metadata during the revise pass.*

### Resulting files

- `SPECIFICATION/constraints.md`
- `SPECIFICATION/scenarios.md`
- `tests/heading-coverage.json`

### Known gap, deliberately not ratified here

The hook modules currently exist as two byte-identical copies —
`.claude/hooks/` (repo-local) and `.claude-plugin/hooks/` (plugin-distributed) —
each independently covered under its own `mirror_pairings` entry, with nothing
asserting they stay in sync. A fix landing in one copy would leave adopters on
the other. This constraint deliberately says "the orchestrator-distributed hook"
in the singular and does NOT bless the duplication; resolving it is tracked as
work-item `bd-ib-1jye.6`. Ratifying a single-source-of-truth requirement now
would make the spec describe a state the repository is not yet in.
