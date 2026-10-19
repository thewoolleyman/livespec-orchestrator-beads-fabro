"""The checkout the plan-resume fixtures track their `required_result` against.

Every plan-resume fixture carries a typed `next_action` whose `required_result`
names a REPOSITORY, and `_plan_result_repository.resolve_result_repository`
treats the project root's own DIRECTORY NAME as that repository's canonical
identity: a name resolves either because it equals `project_root.name` or
because it is a configured `cross_repo_targets` key whose clone exists. A
fixture naming this repository LITERALLY therefore resolves only in a checkout
that happens to be named after the repository.

That is exactly what a secondary checkout is not. A worktree under
`~/.worktrees/<repo>/<branch>` is named after its BRANCH, and the Dispatcher's
post-merge janitor checkout is `~/.worktrees/<repo>/janitor-<item>` — neither
matches the literal, and neither is a configured sibling. The literal then
resolves to nothing, the reading comes back `unobservable`, and every resume
assertion that expects a taken `next_action` fails. Measured 2026-10-12: three
scenario-111 cases plus two sibling files failed in any worktree while the
primary clone and master CI stayed green, so every worktree pre-push and every
post-merge janitor refused on tests nobody could reproduce from the clone.

So the fixtures name the checkout UNDER TEST by that checkout's own directory
name, resolved here from this file rather than from a literal or from the
process working directory. `CHECKOUT_UNDER_TEST` is the one derivation; a
fixture pins it as its `StoreConfig.repo_root` AND names it in its
`required_result`, which keeps the two halves of that resolution one answer
rather than two that can disagree.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = [
    "CHECKOUT_UNDER_TEST",
    "item_status_result",
]

# The repository checkout this test tree belongs to, whatever its directory is
# called. Derived from `__file__` rather than from `Path.cwd()` so a fixture's
# repository identity does not depend on where pytest was invoked from either.
CHECKOUT_UNDER_TEST = Path(__file__).resolve().parents[1]


def item_status_result(*, checkout: Path, item_id: str, status: str) -> dict[str, object]:
    """An `item_status` required_result naming `checkout` by its own directory name.

    `checkout` is a parameter rather than the module constant so this derivation
    is exercisable against a BRANCH-NAMED checkout — the shape the literal could
    not resolve — instead of only against whichever checkout the suite runs in.
    """
    return {
        "repo": checkout.name,
        "item_status": {"item_id": item_id, "status": status},
    }
