# Research — is the codex-companion sandbox problem already known upstream?

**Date:** 2026-07-17. **Question the maintainer asked:** *"Deep research if there are
any existing issues or PRs around this problem. And if not, why not — why are we
breaking new ground?"*

## Bottom line

We are **not** breaking new ground — not on the problem, the fix, or the exact
`file:line`. `openai/codex-plugin-cc` has a dozen-plus issues and 5+ PRs describing
exactly this, some quoting the same `codex.mjs:68/:81` chokepoint. **Zero
sandbox-configurability PRs have ever merged**, and the sharpest root-cause issues sit
with **no maintainer comment at all**. The gap upstream is a *merge*, not awareness.

## Prior art (openai/codex-plugin-cc)

### Issues describing our exact problem

| # | State | Note |
| --- | --- | --- |
| #482 | OPEN | "Hardcoded sandbox values always override config.toml" — quotes `codex.mjs:68/:81`, `codex-companion.mjs:491`, `codex.mjs:1012`, `:414`. Our root cause verbatim. 0 comments. |
| #505 | OPEN | Same environment as ours (Ubuntu 24.04, `apparmor_restrict_unprivileged_userns=1`, bwrap loopback fail, VPS); config.toml `danger-full-access` works for direct CLI, plugin ignores it. 0 comments. |
| #240 | OPEN | "Plugin overrides Codex sandbox config and can trigger bwrap failures." |
| #167 | CLOSED (by author) | "Expose sandbox mode as env var / config knob for review and adversarial-review." A commenter: *"rewriting danger-full-access at scripts/lib/codex.mjs works for me."* |
| #145 | OPEN | "Add `--full-access` flag to companion task for unsandboxed execution." |
| #124 | OPEN | "Support `--dangerously-skip-permissions` (aka yolo) mode for the app server… Shouldn't be a security issue if it's opt-in!" |
| #304 | OPEN | `workspace-write` git push fails with DNS error — the network-off-under-workspace-write wrinkle. |
| #519 | OPEN (07-17) | Broader "plugin-only Codex configuration layer" — newest framing. 0 comments. |

### PRs that tried to fix it — none merged

| # | State | Fate |
| --- | --- | --- |
| #260 | CLOSED **by author** | "use danger-full-access so MCP tool calls work" — our exact fix. Iterated under Codex-bot pushback to an explicit `CODEX_COMPANION_FULL_ACCESS=1` opt-in, then self-withdrawn. |
| #241 | CLOSED **by author** | "Respect Codex sandbox config" via `CODEX_COMPANION_SANDBOX_MODE` (`inherit`/explicit). Bot review passed ("no major issues") — still self-withdrawn. |
| #226 | OPEN, mergeable | `--sandbox` flag + `CODEX_SANDBOX` env (review + task); implements #167. Last touched 2026-04-14 — ~3 months stale, no human review. |
| #147 | OPEN, mergeable | `--full-access` flag; implements #145. ~3 months stale. |
| #508 | OPEN (07-15, freshest) | Resolve task sandbox from config.toml + `task --read-only`; task-path only, no review path, no full-access. |

The only merged PR whose title matched the sandbox/config/env terms was #159 ("inherit
`process.env` in app-server spawn") — unrelated to sandbox mode.

## Why no fix has landed (the "why")

1. **Maintainer non-engagement, not rejection.** All three closed attempts were closed by
   *their own authors* (self-withdrawn), never rejected by OpenAI. The crisp root-cause
   issues (#482, #505, #519) have zero maintainer comments; the live fix PRs (#226, #147)
   are ~3 months stale with only the `chatgpt-codex-connector` bot reviewing. The repo
   *does* merge other external PRs regularly (e.g. #447 on 07-08), so this is targeted
   non-prioritization of the sandbox cluster.
2. **Design fragmentation with no decider.** Five PRs, five shapes: hardcode
   danger-full-access, `CODEX_COMPANION_FULL_ACCESS` env, `CODEX_COMPANION_SANDBOX_MODE=inherit`,
   `--sandbox`+`CODEX_SANDBOX`, `--full-access` flag, config.toml-inherit. With no maintainer
   to converge on one, contributors re-spin and burn out.
3. **A deliberate security posture.** The closest thing to an OpenAI position is the Codex
   bot pushing back on *silently elevating privileges* in #260, which forced the design to
   explicit opt-in. Read-only-by-default (especially for reviews) is intentional — which is
   exactly the tension the plan already surfaced and the maintainer already accepted.
4. **Contributor attrition.** Threading a flag through `createCompanionJob → buildTaskJob →
   buildTaskRequest` and all call sites, then maintaining it against a fast-moving CLI, is
   real work casual contributors abandon.

## What this changed for our decision

- **"Wait for / upstream a PR" (handoff option 3) is a weak bet.** Even a clean, bot-approved
  PR (#241) or a complete flag implementation (#226) sits unmerged for months with no human
  review. → self-carry.
- **Design chosen: force `danger-full-access` at the single chokepoint** with an env
  escape-hatch to downgrade (`process.env.CODEX_COMPANION_SANDBOX || "danger-full-access"`),
  rather than the upstream-flavored "inherit config.toml" approach. Inherit has a
  *silent-degrade* failure mode: if `~/.codex/config.toml` is reset by a codex re-login or
  upgrade, full-access silently drops back to read-only — the exact false-confidence bug we
  are fixing. For a factory that must not silently degrade, forcing at the chokepoint is more
  reliable. `sandbox_mode = "danger-full-access"` is *also* set in config.toml as
  defense-in-depth and to cover the raw `codex exec` path.
- **Durability = cache patch + idempotent SessionStart re-apply hook** (this repo), not a fork
  + host-wide marketplace re-point (more consequential/outward; deferred pending maintainer
  sign-off).
