"""The digest-named attachment a proof too large to publish inline travels as.

`bd-ib-555xcd`: a record is ONE forge comment against a declared budget, and some
proofs are legitimately enormous — a full test-suite transcript, a long log, a
rendered file. The two wrong remedies are silent at the surface: a TRUNCATED proof
still renders as a proof, and a DROPPED assertion reads downstream as one nobody
captured. So a bulky proof is neither cut nor abandoned; it is uploaded to the
proof-asset store and REFERENCED from the record.

WHY THE RECORD CARRIES THREE FIELDS AND NOT JUST A LINK. The name says where the
bytes are and the size says how many to expect, but only the DIGEST says WHICH
bytes. Without it, an asset that was clobbered by a later fix round, truncated
mid-upload, or re-uploaded from a different tree reads as this capture's evidence
while carrying something else — and the replay leg would faithfully reproduce the
wrong thing and publish `verified` for it. The digest is what makes the reference
checkable rather than merely followable, which is the whole difference between
evidence and a pointer.

WHY THE NAME CARRIES THE DIGEST TOO. Two consequences, both wanted. A reader
comparing a record against an asset listing can see at a glance which bytes a name
refers to; and a re-upload of IDENTICAL bytes lands on the IDENTICAL name, so a
fix round re-entering the capture stage is idempotent rather than a clobber of
something subtly different under a name that did not change.

WHY THE BLOCK IS PLAIN LINES AND NOT A FENCE, which is the one placement rule here
that is easy to get wrong and expensive to get wrong. The record reader
(`_dispatcher_proof_record`) deliberately ignores everything inside a fenced block,
because it cannot otherwise tell a `Reproduced:` verdict a verifier AUTHORED from
one a proof merely PRINTED. An attachment reference is authored prose ABOUT the
proof rather than the proof itself, so it has to live outside a fence or no reader
would ever see it.

AND THE READER HERE IS FENCE-AWARE FOR THE MIRROR REASON. A replay whose proof
`cat`s an earlier record PRINTS these very labels inside its own fenced output. A
reader that matched them would attribute ANOTHER assertion's asset to this one, and
then grade this assertion on whether those foreign bytes still hash correctly —
which is a fail-open that looks exactly like a pass. `attached_proof_in` therefore
reads only PROSE, exactly as the verdict scan does.

WHY EVERY PARTIAL READ FAILS CLOSED. Three of the four labels, or a byte size that
will not parse, yields `None` rather than a half-populated value. A partial
attachment would send the digest check after an asset with no digest to compare
against, and the natural coding of "nothing to compare" is "no mismatch found" — a
pass earned by missing data, on the one path whose entire job is to refuse that.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass

__all__: list[str] = [
    "ATTACHED_PROOF_ASSET_LABEL",
    "ATTACHED_PROOF_BYTES_LABEL",
    "ATTACHED_PROOF_DIGEST_LABEL",
    "ATTACHED_PROOF_EXTENSION",
    "ATTACHED_PROOF_LABEL",
    "DIGEST_ALGORITHM",
    "ProofAttachment",
    "attached_proof_in",
    "attached_proof_slug",
    "proof_digest",
]

# The four labels, which are ONE vocabulary shared by the renderer, the reader, and
# the two stage prompts that hand-write them. A label changed here without the
# prompts changing too would publish records no reader could parse, so
# `tests/prompts/test_proof_record_size_budget_discipline.py` binds the prose to
# these constants.
ATTACHED_PROOF_LABEL = "Attached proof"
ATTACHED_PROOF_BYTES_LABEL = "Attached proof bytes"
ATTACHED_PROOF_DIGEST_LABEL = "Attached proof digest"
ATTACHED_PROOF_ASSET_LABEL = "Attached proof asset"

# The digest algorithm, named IN the value rather than assumed by readers: a bare
# hex string does not say which hash produced it, and `sha256sum` on the downloaded
# file is how both verifying surfaces check it.
DIGEST_ALGORITHM = "sha256"

# A text capture is text, whatever it is a capture OF.
ATTACHED_PROOF_EXTENSION = "txt"

# How much of the hex digest the slug carries. Long enough that a collision is not
# a practical concern for the handful of assets one record holds, short enough that
# the name stays readable in a release listing.
_DIGEST_SLUG_HEX = 16

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


@dataclass(frozen=True, kw_only=True)
class ProofAttachment:
    """One bulky proof, as the record references it.

    `size_bytes` is the size of the UPLOADED FILE, not of anything rendered here,
    and `digest` is taken over those same bytes — so a verifier can reproduce both
    from the downloaded asset alone, with no access to the record's own rendering.
    """

    name: str
    size_bytes: int
    digest: str
    url: str

    def render(self) -> str:
        """The four plain lines that stand where the fenced inline proof would."""
        return "\n".join(
            [
                f"{ATTACHED_PROOF_LABEL}: {self.name}",
                f"{ATTACHED_PROOF_BYTES_LABEL}: {self.size_bytes}",
                f"{ATTACHED_PROOF_DIGEST_LABEL}: {self.digest}",
                f"{ATTACHED_PROOF_ASSET_LABEL}: {self.url}",
            ]
        )


def proof_digest(*, text: str) -> str:
    """The algorithm-qualified digest of one proof's UTF-8 bytes.

    Over BYTES rather than characters because the asset IS bytes: a digest taken
    over anything else could not be reproduced by `sha256sum` on the downloaded
    file, which is precisely how the replay stage and the acceptance pass check it.
    """
    return f"{DIGEST_ALGORITHM}:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def attached_proof_slug(*, digest: str) -> str:
    """The ratified name's `slug` field for an attachment: the digest, abbreviated.

    Lowercase-kebab, as the naming clause requires of a slug, and carrying the
    algorithm so the slug says what kind of fingerprint it is rather than looking
    like an arbitrary hex token.
    """
    algorithm, _, hexdigest = digest.partition(":")
    return f"proof-{algorithm}-{hexdigest[:_DIGEST_SLUG_HEX]}"


def attached_proof_in(*, section: Sequence[str]) -> ProofAttachment | None:
    """The attachment one assertion's section REFERENCES, or `None` for none.

    Reads only PROSE: a label printed inside a proof's own fenced output is output
    that happens to look like a reference, and attributing it to this assertion
    would point the digest check at another assertion's asset (see the module
    docstring). The fence tracking is the same rule the record reader applies, kept
    simple here because a caller hands this one CONTIGUOUS section whose first line
    is never inside a fence.

    All four labels are required. A partial block fails closed — see the module
    docstring for why a half-populated attachment is worse than none.
    """
    fields = _prose_fields(section=section)
    name = fields.get(ATTACHED_PROOF_LABEL)
    raw_size = fields.get(ATTACHED_PROOF_BYTES_LABEL)
    digest = fields.get(ATTACHED_PROOF_DIGEST_LABEL)
    url = fields.get(ATTACHED_PROOF_ASSET_LABEL)
    if name is None or raw_size is None or digest is None or url is None:
        return None
    if not raw_size.isdigit():
        return None
    return ProofAttachment(name=name, size_bytes=int(raw_size), digest=digest, url=url)


def _prose_fields(*, section: Sequence[str]) -> dict[str, str]:
    """Each attachment label found OUTSIDE a fence, mapped to its value.

    The longest matching label wins, which is what keeps `Attached proof` from
    swallowing `Attached proof bytes`: the shorter label is a prefix of the longer
    one up to its colon, so a first-match scan over an unordered label set would
    read the wrong field depending on iteration order.
    """
    found: dict[str, str] = {}
    fence: str | None = None
    for line in section:
        delimiter = _FENCE.match(line)
        if delimiter is not None:
            fence = _fence_after(fence=fence, delimiter=delimiter.group(1))
            continue
        if fence is not None:
            continue
        _record_field(found=found, line=line.strip())
    return found


def _record_field(*, found: dict[str, str], line: str) -> None:
    """Note the attachment label this prose line carries, if it carries one."""
    for label in _LABELS_LONGEST_FIRST:
        prefix = f"{label}:"
        if line.startswith(prefix):
            found[label] = line[len(prefix) :].strip()
            return


def _fence_after(*, fence: str | None, delimiter: str) -> str | None:
    """The open fence after one delimiter line, or `None` outside a fence.

    The OPEN delimiter is carried rather than a boolean for the reason the record
    reader carries it: a proof legitimately nests one fence inside another, and a
    boolean inverts on the inner delimiter and stays inverted, after which the rest
    of the section reads as fenced and a real reference becomes invisible.
    """
    if fence is None:
        return delimiter
    if delimiter[0] == fence[0] and len(delimiter) >= len(fence):
        return None
    return fence


# Longest first, so a label that is a prefix of another cannot claim its line.
_LABELS_LONGEST_FIRST = tuple(
    sorted(
        (
            ATTACHED_PROOF_LABEL,
            ATTACHED_PROOF_BYTES_LABEL,
            ATTACHED_PROOF_DIGEST_LABEL,
            ATTACHED_PROOF_ASSET_LABEL,
        ),
        key=len,
        reverse=True,
    )
)
