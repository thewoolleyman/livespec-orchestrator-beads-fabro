"""The carry-forward DECISION, as the sandbox computes it.

`SPECIFICATION/contracts.md` section "Definition-of-Done and Proof-of-Done
stages" -> "The decision" (v138) requires a changed-head `pr_refresh` to settle,
"by a deterministic rule from repository and record state alone", whether the
run's verified proof still covers the new head -- and says in as many words that
"no language-model judgement MAY take part in it". This fragment is that rule.
Nothing here calls a model, and nothing here can: the only subprocesses it spawns
are `git`, `gh` and the step commands the direct-read grammar admits.

WHY EVERY REFUSAL NAMES ITS OWN INPUT. The clause enumerates the inputs a
`reproof_required` record must name -- an incoming path outside every inert
class or inside the observation scope or item paths, a step outside the grammar,
a rejected path operand, the differing patch identities, a path whose blob
identity differs, a path whose read identity is missing or differs, a step whose
replay did not reproduce, a captured proof that is not one fenced block, or the
input that could not be read. Those are NINE different findings with nine
different remedies, and a shared "the proof no longer covers this head" would
make them one. So each check appends its own finding and the record carries them
all, rather than returning on the first.

WHY THE CHECKS THAT CAN RUN ALL RUN. A step outside the grammar makes the
observation scope unestablishable, so the scope-dependent checks are skipped --
but the incoming-path classification does NOT depend on the scope, and skipping
it would hide a second, independent reason the refresh re-proves. One run of the
decision therefore reports everything it could measure, which is what makes the
record a work order rather than a verdict.

WHY AN UNREADABLE INPUT STILL POSTS A RECORD. The clause requires exactly one
decision record on every changed-head refresh and requires the unreadable input
to be NAMED. A stage that failed closed in silence there would leave the one
durable artifact absent for precisely the condition hardest to reconstruct
afterwards -- so the unreadable arm renders a `reproof_required` record stating
the input it could not read and stating, as unavailable, each field that input
would have supplied.

WHY THE REPLAY COMPARISON IS OVER LINES. The clause asks for standard output
"byte for byte identical to that step's captured proof, which MUST be the single
fenced text block the verified record gives for that step". A Markdown fenced
block DELIMITS LINES: its content has no representation for a missing or extra
trailing newline, so "the bytes of the block" is only defined up to that one
difference. The comparison is therefore over the two line sequences, which is the
strongest relation the record's own encoding can carry. Anything else -- a
trailing-whitespace difference, a reordering, one changed character -- is a
difference and re-proves.

WHY THE REPLAY EXECUTES WITHOUT A SHELL. The grammar has already established
that the command contains no shell metacharacter and splits into literal words,
so there is nothing a shell would add except the one capability the grammar
exists to exclude. Spawning the word list directly is what makes that exclusion
structural rather than careful.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_provenance import (
    FACTORY_RUN_ID_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_TITLE,
    VERDICT_CARRIED_FORWARD,
    VERDICT_REPROOF_REQUIRED,
    VERDICT_VERIFIED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_anchor import (
    PUBLISH_HEAD_LABEL,
)

__all__: list[str] = [
    "DECISION_PLAN_STORE_CLASS",
    "decision_fragment",
]

# The plan store, the first of the three inert classes. Spelled here because the
# other two are derived from the repository's own `spec_root`, so this is the
# only one a reader could otherwise mistake for configuration.
DECISION_PLAN_STORE_CLASS = "plan/"

# The decision, the record it renders, and the main the node enters. A RAW outer
# string, so every backslash below is the one the inner source needs.
_DECISION_FRAGMENT = r'''
import json
import os
import shlex
import subprocess
import sys

PLAN_STORE = "__PLAN_STORE__"
RECORD_TITLE = "__RECORD_TITLE__"
VERDICT_CARRIED_FORWARD = "__CARRIED_FORWARD__"
VERDICT_REPROOF_REQUIRED = "__REPROOF_REQUIRED__"
VERDICT_VERIFIED = "__VERIFIED__"
RUN_ID_MARKER = "__RUN_ID_MARKER__"
HEAD_LABEL = "__HEAD_LABEL__"
EM_DASH = "—"
REPLAY_LOCALE = "C.UTF-8"
UNAVAILABLE = "unavailable"
TREE_MODE = "040000"
REGULAR_FILE_MODES = ("100644", "100755")


class Unreadable(Exception):
    """A decision input that could not be read or computed, naming itself."""

    def __init__(self, named):
        super().__init__(named)
        self.named = named


def run_git(argv, named):
    """One git reading, or `Unreadable` naming what could not be computed."""
    result = subprocess.run(
        ["git", *argv], capture_output=True, text=True, check=False,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise Unreadable(named + " (git " + " ".join(argv) + ": "
                         + result.stderr.strip() + ")")
    return result.stdout


def repository_root():
    return run_git(["rev-parse", "--show-toplevel"], "the repository root").strip()


def factory_run_identity():
    """The dispatch this sandbox was provisioned by, or None when undeclared.

    Read from the clone's own config, where the Dispatcher's provenance prepare
    step writes it. An absent marker is NOT unreadable: a direct caller that
    minted no dispatch id declares none, and the record then names no run rather
    than failing the whole decision over a header field.
    """
    result = subprocess.run(
        ["git", "config", "--get", RUN_ID_MARKER], capture_output=True, text=True,
        check=False, stdin=subprocess.DEVNULL,
    )
    return result.stdout.strip() or None


def spec_root(root):
    """The repository's declared `spec_root`, or `Unreadable` naming the file.

    `//` line comments only, which is the form `.livespec.jsonc` uses across
    this family and the form the package's own JSONC reader admits. A file that
    does not parse is an unreadable DECISION INPUT rather than a crash, because
    two of the three inert classes are derived from this value.
    """
    path = os.path.join(root, ".livespec.jsonc")
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as error:
        raise Unreadable("the repository configuration .livespec.jsonc ("
                         + str(error) + ")")
    stripped = re.sub(r'("(?:\\.|[^"\\])*")|(//[^\n]*)',
                      lambda m: m.group(1) or "", text)
    try:
        value = json.loads(stripped).get("spec_root")
    except ValueError as error:
        raise Unreadable("the repository configuration .livespec.jsonc ("
                         + str(error) + ")")
    if not isinstance(value, str) or not value:
        raise Unreadable("the repository configuration .livespec.jsonc "
                         "(no spec_root declared)")
    return value


def inert_prefixes(head, root):
    """Every inert class prefix, measured at ONE head.

    The template histories are enumerated AT THE HEAD BEING EXAMINED, exactly as
    the clause says, so a template directory the incoming commits ADD is inert at
    the new head and a directory they remove stops being inert -- neither of
    which a fixed list could express.
    """
    prefixes = [PLAN_STORE, spec_root(root) + "/history/"]
    listing = run_git(["ls-tree", "--name-only", head,
                       spec_root(root) + "/templates/"],
                      "the template directories at " + head)
    for line in listing.splitlines():
        name = line.strip().rstrip("/")
        if name:
            prefixes.append(name + "/history/")
    return prefixes


def beneath_any(path, prefixes):
    return any(path.startswith(prefix) for prefix in prefixes)


def name_only(base, head, named):
    """`git diff --name-only --no-renames <base> <head>`, as a list."""
    listing = run_git(["diff", "--name-only", "--no-renames", base, head], named)
    return [line for line in listing.splitlines() if line]


def patch_identity(base, head, named):
    """The stable patch identity of `<base>..<head>`, or `Unreadable`."""
    diff = run_git(["diff", "--no-color", "--no-ext-diff", "--no-renames",
                    "--full-index", base, head], named)
    result = subprocess.run(["git", "patch-id", "--stable"], input=diff,
                            capture_output=True, text=True, check=False)
    if result.returncode != 0 or not result.stdout.split():
        raise Unreadable(named + " (git patch-id --stable printed nothing)")
    return result.stdout.split()[0]


def tree_mode(head, path):
    """The mode one path carries in one head's tree, or None when it carries none."""
    result = subprocess.run(["git", "ls-tree", head, "--", path],
                            capture_output=True, text=True, check=False,
                            stdin=subprocess.DEVNULL)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return result.stdout.split()[0]


def names_a_regular_file(head, path):
    """Whether `path` reaches a regular, non-symlinked file through real directories.

    Every LEADING component is checked as well as the path itself, because a
    symlinked parent makes the read reach somewhere the path does not name -- and
    `git ls-tree` answers nothing for a path under a symlink, which would read as
    a missing file rather than as the aliasing it is.
    """
    parts = path.split("/")
    for index in range(len(parts) - 1):
        if tree_mode(head, "/".join(parts[: index + 1])) != TREE_MODE:
            return False
    return tree_mode(head, path) in REGULAR_FILE_MODES


def blob_identity(head, path):
    """The blob one path carries at one head, or None when it carries none."""
    result = subprocess.run(["git", "rev-parse", head + ":" + path],
                            capture_output=True, text=True, check=False,
                            stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def worktree_identity(path, root):
    """The raw identity of one working-tree file, or None when it cannot be taken."""
    result = subprocess.run(["git", "hash-object", "--no-filters", "--", path],
                            cwd=root, capture_output=True, text=True, check=False,
                            stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        return None
    return (result.stdout.strip() or None)


def replay(command, root):
    """Execute one admitted command at the new head, and return its stdout lines.

    None means it could not execute, which the clause treats exactly as output
    that differed. Standard input is CLOSED and `LC_ALL` is pinned, because both
    are inputs the verified execution had and neither is recorded: a step whose
    output depends on the ambient locale would otherwise differ for a reason the
    record cannot show.
    """
    environ = dict(os.environ)
    environ["LC_ALL"] = REPLAY_LOCALE
    try:
        result = subprocess.run(shlex.split(command), cwd=root, env=environ,
                                capture_output=True, text=True, check=False,
                                stdin=subprocess.DEVNULL)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.splitlines()


def latest_verified_record(number):
    """The newest `verified` record on the pull request, as (url, body, head).

    The NEWEST rather than one selected by run attribution, which is the same
    reading `_dispatcher_publication_head` takes and for the same reason: only
    `proof_verify` precedes publication, so in any conforming run the newest
    `verified` record IS this run's verification. The record's own identity
    field is carried into the decision record, so a reader can still see which
    run published the proof being carried.
    """
    result = subprocess.run(["gh", "pr", "view", str(number), "--json", "comments"],
                            capture_output=True, text=True, check=False,
                            stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        raise Unreadable("the pull request's comments (gh: "
                         + result.stderr.strip() + ")")
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        raise Unreadable("the pull request's comment payload (it did not parse "
                         "as JSON)")
    comments = payload.get("comments")
    if not isinstance(comments, list):
        raise Unreadable("the pull request's comment payload (it carries no "
                         "comments array)")
    found = None
    for one in comments:
        if not isinstance(one, dict):
            continue
        body = one.get("body") or ""
        if record_verdict(body) == VERDICT_VERIFIED:
            found = (one.get("url") or UNAVAILABLE, body, published_head(body))
    if found is None:
        raise Unreadable("the latest verified Proof of Done record (the pull "
                         "request carries none)")
    if found[2] is None:
        raise Unreadable("the latest verified Proof of Done record's "
                         "publish-branch head (it names no single full sha)")
    return found
'''

# The scope walk, the condition ladder, the record render and the main. Split
# from the fragment above only to keep each string reviewable; they are
# concatenated in order and share one namespace.
_LADDER_FRAGMENT = r'''

def observation_scope(steps, root, verified_head, new_head, findings):
    """The canonical path operands of every step, or None when the scope is not establishable.

    None rather than an empty set, because an empty scope is a real answer -- a
    proof whose only step is a `git show` of a path that exists at both heads has
    a one-element scope, and a proof with no steps at all would have none -- while
    "not establishable" must stop every scope-dependent check. Collapsing the two
    would compare incoming paths against an empty scope and find no overlap,
    which is a PASS earned by missing data.
    """
    scope = []
    establishable = bool(steps)
    if not steps:
        findings.append("step-outside-direct-read-grammar: the verified record "
                        "carries no numbered reproduction step")
    for step in steps:
        command, reason = step_command(step)
        if command is None:
            findings.append("step-outside-direct-read-grammar: step "
                            + step["number"] + " " + reason)
            establishable = False
            continue
        graded = classify_command(command)
        if not graded["inside"]:
            findings.append("step-outside-direct-read-grammar: step "
                            + step["number"] + " " + graded["reason"])
            establishable = False
            continue
        step["command"] = command
        step["working_tree"] = graded["working_tree"]
        step["operands"] = []
        for operand in graded["operands"]:
            path = canonical_path(operand)
            if path is None:
                findings.append("rejected-path-operand: step " + step["number"]
                                + " names " + repr(operand)
                                + ", which is absolute, empty or carries a "
                                  "parent segment")
                establishable = False
                continue
            if not names_a_regular_file(verified_head, path):
                findings.append("rejected-path-operand: step " + step["number"]
                                + " names " + path + ", which does not reach a "
                                  "regular non-symlinked file at the verified "
                                  "head " + verified_head)
                establishable = False
                continue
            if not names_a_regular_file(new_head, path):
                findings.append("rejected-path-operand: step " + step["number"]
                                + " names " + path + ", which does not reach a "
                                  "regular non-symlinked file at the new head "
                                + new_head)
                establishable = False
                continue
            step["operands"].append(path)
            scope.append(path)
    return sorted(set(scope)) if establishable else None


def check_captured_proofs(steps, findings):
    """Every step must give exactly one fenced text block as its captured proof."""
    for step in steps:
        if len(step["proofs"]) != 1:
            findings.append("captured-proof-not-one-fenced-block: step "
                            + step["number"] + " gives "
                            + str(len(step["proofs"]))
                            + " fenced text blocks")


def check_incoming(incoming, prefixes, scope, item_paths, findings):
    """Classify every incoming path against the inert classes, the scope and the item."""
    for path in incoming:
        if not beneath_any(path, prefixes):
            findings.append("incoming-path-outside-inert-classes: " + path)
        if scope is not None and path in scope:
            findings.append("incoming-path-in-observation-scope: " + path)
        if path in item_paths:
            findings.append("incoming-path-in-item-paths: " + path)


def check_blob_identities(paths, verified_head, new_head, findings):
    """Every observed and item path carries one blob at both heads, or none at both."""
    for path in paths:
        if blob_identity(verified_head, path) != blob_identity(new_head, path):
            findings.append("blob-identity-differs: " + path)


def check_read_identities(steps, declared, root, findings):
    """Every working-tree path operand's recorded identity equals the new head's bytes."""
    for step in steps:
        if not step.get("working_tree"):
            continue
        for path in step["operands"]:
            recorded = declared.get(path)
            if recorded is None:
                findings.append("read-identity-missing: " + path)
                continue
            if recorded != (worktree_identity(path, root) or ""):
                findings.append("read-identity-differs: " + path)


def check_replay(steps, root, findings):
    """Every step's command reproduces its captured proof at the new head."""
    for step in steps:
        if len(step["proofs"]) != 1:
            continue
        produced = replay(step["command"], root)
        if produced is None or produced != step["proofs"][0].splitlines():
            findings.append("mechanical-replay-did-not-reproduce: step "
                            + step["number"])


def decide(args):
    """The whole decision, as (verdict, findings, facts) with nothing raised."""
    facts = {"decision": None, "verified_record": UNAVAILABLE,
             "verified_head": UNAVAILABLE, "previous_head": args["previous_head"],
             "new_head": args["new_head"],
             "incoming_range": args["previous_base"] + ".." + args["new_base"],
             "incoming_paths": None, "observation_scope": None,
             "verified_patch_identity": UNAVAILABLE,
             "new_patch_identity": UNAVAILABLE}
    findings = []
    try:
        root = repository_root()
        url, body, verified_head = latest_verified_record(args["pull_request"])
        facts["verified_record"] = url
        facts["verified_head"] = verified_head
        incoming = name_only(args["previous_base"], args["new_base"],
                             "the incoming paths")
        facts["incoming_paths"] = incoming
        verified_base = run_git(["merge-base", verified_head, args["new_base"]],
                                "the verified base").strip()
        item_paths = name_only(verified_base, verified_head, "the item paths")
        facts["verified_patch_identity"] = patch_identity(
            verified_base, verified_head, "the verified patch identity")
        facts["new_patch_identity"] = patch_identity(
            args["new_base"], args["new_head"], "the new patch identity")
        prefixes = inert_prefixes(args["new_head"], root)
        declared_directory = declared_working_directory(body)
        steps = reproduction_steps(body)
        if declared_directory != ".":
            findings.append("step-outside-direct-read-grammar: the verified "
                            "record declares the working directory "
                            + (repr(declared_directory)
                               if declared_directory is not None else "nothing")
                            + " rather than the repository root, so every step "
                              "is outside the grammar")
            scope = None
        else:
            scope = observation_scope(steps, root, verified_head,
                                      args["new_head"], findings)
        facts["observation_scope"] = scope
        check_captured_proofs(steps, findings)
        check_incoming(incoming, prefixes, scope, item_paths, findings)
        if facts["verified_patch_identity"] != facts["new_patch_identity"]:
            findings.append("patch-identity-differs: the verified diff is "
                            + facts["verified_patch_identity"]
                            + " and the refreshed diff is "
                            + facts["new_patch_identity"])
        if scope is not None:
            check_blob_identities(sorted(set(scope) | set(item_paths)),
                                  verified_head, args["new_head"], findings)
            check_read_identities(steps, read_identities(body), root, findings)
            check_replay(steps, root, findings)
    except Unreadable as unreadable:
        findings.append("unreadable-input: " + unreadable.named)
    verdict = (VERDICT_CARRIED_FORWARD if not findings
               else VERDICT_REPROOF_REQUIRED)
    facts["decision"] = verdict
    return verdict, findings, facts


def render(verdict, findings, facts, timestamp, run_identity):
    """The decision record, rendered through the one renderer either verdict has."""
    identity = "run " + run_identity if run_identity else "run " + UNAVAILABLE
    lines = [" ".join([RECORD_TITLE, EM_DASH, verdict, EM_DASH, identity,
                       EM_DASH, timestamp]), ""]
    lines.append(HEAD_LABEL + ": " + facts["new_head"])
    lines.extend(["", "## Carry-forward decision", ""])
    lines.append("Decision: " + verdict)
    lines.append("Verified record: " + facts["verified_record"])
    lines.append("Verified head: " + facts["verified_head"])
    lines.append("Previous published head: " + facts["previous_head"])
    lines.append("New head: " + facts["new_head"])
    lines.append("Incoming range: " + facts["incoming_range"])
    lines.append("Incoming paths: " + _listed(facts["incoming_paths"]))
    lines.append("Observation scope: " + _listed(facts["observation_scope"]))
    lines.append("Verified patch identity: " + facts["verified_patch_identity"])
    lines.append("New patch identity: " + facts["new_patch_identity"])
    if findings:
        lines.extend(["", "## Inputs that decided it", ""])
        lines.extend("- " + finding for finding in findings)
    return "\n".join(lines) + "\n"


def _listed(values):
    """One decision field's paths, or a word saying which kind of absence it is."""
    if values is None:
        return UNAVAILABLE
    return ", ".join(values) if values else "none"


def post(number, body, root):
    """Post the decision record, and report whether the forge accepted it."""
    path = os.path.join(root, ".git", "livespec-carry-forward-record.md")
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
    except OSError as error:
        return "the decision record could not be written for posting: " + str(error)
    result = subprocess.run(["gh", "pr", "comment", str(number), "--body-file", path],
                            capture_output=True, text=True, check=False,
                            stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        return ("the decision record could not be posted on pull request #"
                + str(number) + ": " + result.stderr.strip())
    return None


def parse_argv(argv):
    """The six values `pr_refresh_head` hands down, or None when one is absent."""
    names = ("--pull-request", "--default-branch", "--previous-head",
             "--previous-base", "--new-base", "--new-head")
    found = {}
    for index, token in enumerate(argv):
        if token in names and index + 1 < len(argv):
            found[token[2:].replace("-", "_")] = argv[index + 1]
    return found if len(found) == len(names) else None


def main(argv):
    args = parse_argv(argv)
    if args is None:
        sys.stderr.write("LIVESPEC_CARRY_FORWARD_USAGE: --pull-request, "
                         "--default-branch, --previous-head, --previous-base, "
                         "--new-base and --new-head are all required\n")
        return 1
    verdict, findings, facts = decide(args)
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    body = render(verdict, findings, facts, timestamp, factory_run_identity())
    try:
        root = repository_root()
    except Unreadable as unreadable:
        sys.stderr.write("LIVESPEC_CARRY_FORWARD_REPROOF: the repository root "
                         "could not be read (" + unreadable.named + "), so the "
                         "decision record cannot be staged; re-proving\n")
        return 1
    failure = post(args["pull_request"], body, root)
    if failure is not None:
        sys.stderr.write("LIVESPEC_CARRY_FORWARD_POST_FAILED: " + failure
                         + "; the decision was " + verdict + " and a decision "
                         "whose record cannot be posted re-proves, so this run "
                         "returns to proof_capture for " + facts["new_head"]
                         + "\n")
        return 1
    if verdict == VERDICT_CARRIED_FORWARD:
        sys.stderr.write("LIVESPEC_CARRY_FORWARD_CARRIED: the verified proof on "
                         + facts["verified_head"] + " covers the new head "
                         + facts["new_head"] + ", because every incoming path of "
                         + facts["incoming_range"] + " is beneath an inert class "
                         "and outside the observation scope, both patch "
                         "identities are " + facts["new_patch_identity"]
                         + ", and the mechanical replay reproduced every "
                           "captured proof; proceeding to pr\n")
        return 0
    sys.stderr.write("LIVESPEC_CARRY_FORWARD_REPROOF: the verified proof does "
                     "not cover " + facts["new_head"] + "; the inputs that "
                     "decided it are:\n")
    for finding in findings:
        sys.stderr.write("  - " + finding + "\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def decision_fragment() -> str:
    """The decision's exact bytes, with every owned spelling substituted.

    A function rather than a constant for the reason `proof_head_program_source`
    gives: a reader must be able to see that the record title, the three
    verdicts, the publish-head label and the provenance config key came from the
    modules that own them, not from literals typed twice.
    """
    return (
        (_DECISION_FRAGMENT + _LADDER_FRAGMENT)
        .replace("__PLAN_STORE__", DECISION_PLAN_STORE_CLASS)
        .replace("__RECORD_TITLE__", PROOF_RECORD_TITLE)
        .replace("__CARRIED_FORWARD__", VERDICT_CARRIED_FORWARD)
        .replace("__REPROOF_REQUIRED__", VERDICT_REPROOF_REQUIRED)
        .replace("__VERIFIED__", VERDICT_VERIFIED)
        .replace("__RUN_ID_MARKER__", FACTORY_RUN_ID_MARKER)
        .replace("__HEAD_LABEL__", PUBLISH_HEAD_LABEL)
    )
