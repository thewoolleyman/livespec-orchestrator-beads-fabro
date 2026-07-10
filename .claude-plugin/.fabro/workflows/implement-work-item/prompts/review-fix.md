# Review-fix stage — the reviewer flagged blocking issues

The review stage (a senior-engineer code review) returned BLOCKING
findings on this branch's change. Its findings are in the prior stage
context above, each tagged `[BLOCKING]` or `[ADVISORY]`.

## Your assignment (unchanged)

{{ goal }}

## What to do

1. Read the reviewer's `[BLOCKING]` findings. Ignore `[ADVISORY]` ones
   unless a fix is trivial AND clearly in scope — advisories do not gate.
2. For EACH `[BLOCKING]` finding, do exactly one of:
   - **Fix it** in this clone, strictly within the work-item's scope; OR
   - **Reject it** with a one-line rationale when it is out-of-scope,
     not-applicable, or wrong. You are the implementer — you may decline a
     finding you judge incorrect or beyond this work-item. State the
     rationale plainly; the next review pass is told to HONOR it unless it
     is a genuine correctness/security defect.
   Do NOT expand scope to satisfy a finding: a "fix" that adds features,
   abstractions, or refactors the work-item did not ask for is itself
   wrong — prefer REJECTING such a finding with that rationale.
   A `[BLOCKING]` finding must NOT be resolved by EVADING the check that
   would catch it — see the HONEST checks rule below. If the honest fix
   conflicts with a legitimate, required pattern the check over-applies
   to, that is a needs-human `failed` outcome, not a dodge.
3. Honor every rule from the implement stage: no `--no-verify` (if a hook
   fails, fix the cause or end with the needs-human protocol below,
   reporting its output verbatim); `mise exec -- git ...` for all git
   writes; Red-Green-Replay for any product `.py` change (a test-file
   change means a fresh Red commit, never an edit under an existing
   Green); commit trailer `Co-Authored-By: Claude Fable 5
   <noreply@anthropic.com>`; never create or switch branches, never touch
   `.beads/` or `core.bare`.
4. Re-run `mise exec -- just check` yourself until it is green — the
   janitor re-validates this clone after this stage.
5. In your final reply, summarize EACH blocking finding as either
   `FIXED — <what you changed>` or `REJECTED — <one-line rationale>`.

## HONEST checks — no detector evasion (non-negotiable)

Make every check pass HONESTLY — by satisfying the condition it exists
to enforce, never by hiding the violation from its detector. A green
tree obtained by evasion is a FAILED outcome, not a success. This stage
is where such dodges have been authored under pressure from a
`[BLOCKING]` finding; resolving a finding by evasion is itself a
failure. Specifically FORBIDDEN:

- Forking or repointing a shared `livespec_dev_tooling` check to a
  weaker local copy; editing `dev-tooling/checks/**` or changing a
  `check-*` justfile recipe to invoke anything other than the pinned
  `python -m livespec_dev_tooling.checks.<module>`.
- Rewriting a banned call into a form the matcher doesn't recognize but
  that does the same thing (e.g. `sys.stdout.write`/`sys.stderr.write`
  → `.buffer.write`).
- Constructing a class dynamically (`type(name, (Base,), ...)`) or
  otherwise restructuring code to hide a disallowed inheritance/pattern
  from an AST check.
- Silencing a check with `: Any`, `# type: ignore`, `# noqa`, symbol
  renames, or getattr/indirection instead of satisfying it.

If a check genuinely conflicts with a LEGITIMATE, required pattern —
i.e. the check over-applies (a domain exception that must subclass a
stdlib error; a launcher that can't carry `__all__`; a module correctly
invoked via `python -m`) — that is NOT yours to resolve by evasion or by
weakening the check. SURFACE it via the needs-human protocol: end with
`{"outcome":"failed","failure_reason":"check <name> over-applies to
<legitimate pattern> at <file>; needs an upstream gate decision"}` so a
maintainer fixes the check upstream. Reserve this for a genuine
check-vs-legitimate-pattern conflict, not a check you simply find
inconvenient to satisfy.

## When you cannot proceed (needs-human protocol)

If a finding needs a human decision, is NOT caused by this branch's
changes, or you have proven you cannot legitimately resolve it, do NOT go
quiet and do NOT paper over it. End your final reply with the failed
outcome and a STRUCTURED reason, as a JSON object on the last line:

    {"outcome": "failed", "failure_reason": "<what is blocked; what you tried; what decision is needed>"}

When the loop's budget exhausts, the graph parks the run at an in-loop
human gate; your structured reason is what the operator reads first —
make it actionable.
