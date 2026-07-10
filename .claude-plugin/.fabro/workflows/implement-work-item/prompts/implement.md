# Implement stage — one work-item, family discipline

## Your assignment

{{ goal }}

## Where you are

You are in an ISOLATED Fabro sandbox clone of the repo, already checked
out on a Fabro-managed run branch (verify: `git rev-parse --abbrev-ref
HEAD` — it is NOT master). This clone is the secondary-worktree
EQUIVALENT under the family discipline: every rule below applies
unchanged. Do NOT create or switch branches; commit on the current
branch. Do all work inside this clone.

Before writing any code, read the repo's binding rules: `AGENTS.md`
and/or `CLAUDE.md` at the repo root, plus the `CLAUDE.md` of any
directory you edit in. Those files are authoritative for local
constraints.

## Hard rules (non-negotiable)

- NEVER pass `--no-verify` to any git command. If a hook fails, fix the
  cause; if you cannot, report the hook output verbatim and end with
  the needs-human protocol below.
- Always run git write operations through mise so the hooks fire:
  `mise exec -- git add ...`, `mise exec -- git commit ...`.
- NEVER run `git checkout master`, never run `git config core.bare
  true`, never force-push a SHARED or PROTECTED ref (master, release
  branches, any ref someone else is building on). Rewriting THIS run's
  own unmerged, unpublished work (e.g. reshaping commits into the
  Red→Green shape to fix RGR-shape failures before the PR stage
  publishes) is the prescribed remedy, not a violation.
- Never run `bd init`. Never write to any `.beads/` directory.
- Do NOT push or open a PR in this stage — a later stage owns that.
- SCOPE-MINIMALISM: edit ONLY what the work-item requires. Do NOT touch
  unrelated files, unrelated docs, or adjacent cleanup that is not necessary
  to satisfy the assignment and its acceptance criteria.
- ACCEPTANCE-CRITERIA SCOPE — downstream review is NOT yours to run.
  Satisfy only the acceptance conditions you can verify YOURSELF in this
  sandbox: the code/behavior change, its tests, and a green `mise exec --
  just check`. An acceptance line that names a DOWNSTREAM gate — an
  "independent"/"external"/"adversarial" reviewer, a separate NO-BLOCKERS
  review "before acceptance", a human sign-off, a ratification step — is
  handled AFTER this stage by a later `review` node and by the external
  overseer; it is NOT your job. Do the implementation those criteria
  describe, but NEVER spawn a reviewer, run an adversarial review, or block
  waiting on one. If the only acceptance work left is such a downstream
  review gate, you are DONE — end with a success outcome, not the
  needs-human protocol.
- Python style (when the repo is Python): keyword-only arguments
  (`*` separator) on every `def`; `kw_only=True` dataclasses; pyright
  strict must stay clean; expected errors ride dry-python/returns
  Result rails, bugs raise. Never write the abbreviation "NFR" — spell
  out "non-functional-requirements".

### HONEST checks — no detector evasion (non-negotiable)

Make every check pass HONESTLY — by satisfying the condition it exists
to enforce, never by hiding the violation from its detector. A green
tree obtained by evasion is a FAILED outcome, not a success.
Specifically FORBIDDEN:

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

## Red-Green-Replay (REQUIRED for any product `.py` change — follow VERBATIM)

1. **Red commit.** Stage the test file ALONE (no impl) and commit with a
   `fix:`/`feat:` subject. The `red_green_replay` hook runs pytest on
   the staged tree; the staged test MUST fail (non-zero). Prefer a
   genuine assertion failure over ImportError: if the impl module does
   not exist yet, create a minimal STUB on disk so the test imports and
   runs but its assertion FAILS; the stub must NOT make the test pass
   (that trips `test-passed-at-red`). The impl must be UNMODIFIED on
   disk at Red (the hook's pytest reads the on-disk module).
2. **Green amend.** Stage the impl, `mise exec -- git commit --amend`.
   The hook re-runs the SAME test (now passing) and records
   `TDD-Green-*` trailers. Test-file bytes MUST be byte-identical
   across Red→Green; to change the test, author a fresh Red.

Exempt: changesets with no product `.py` (docs, spec, work-items,
config) use `chore(...)`/`docs(...)`/`chore(spec):` subjects and skip
the ritual.

Every commit message body MUST end with the trailer line:

    Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>

## When you are genuinely stuck (needs-human protocol)

If the task is ambiguous, requires a human decision, or is proven not
auto-resolvable (e.g. a hook rejection you cannot legitimately fix), do
NOT go quiet and do NOT paper over it. End your final reply with the
failed outcome and a STRUCTURED reason, as a JSON object on the last
line:

    {"outcome": "failed", "failure_reason": "<what is blocked; what you tried; what decision is needed>"}

The graph routes a failed outcome to an in-loop human gate where an
operator answers and routes the run back into the loop. Reserve it for
genuine blockers — a failing check you can fix is YOUR job, not the
operator's.

## What to do

1. Read the assignment and the relevant code/spec until you understand
   the change.
2. Implement it via the ritual above, in as few cohesive commits as the
   work naturally splits into (test+impl land atomically in one commit).
3. Run the repo's check suite yourself (`mise exec -- just check`) and
   fix what it surfaces — a later janitor stage re-runs it as a hard
   gate, so hand it a green tree. Green must be earned honestly — see
   the HONEST checks rule above; a check-vs-legitimate-pattern conflict
   is a needs-human `failed` outcome, not something to evade.
4. In your final reply, summarize what you changed, list the commits
   (`git log --oneline origin/master..HEAD`), and report any deviation
   or hook output verbatim.
