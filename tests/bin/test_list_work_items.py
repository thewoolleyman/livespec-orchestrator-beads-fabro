"""Per-wrapper coverage test for bin/list_work_items.py."""

from collections.abc import Callable


def test_list_work_items_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "list_work_items.py",
        "livespec_impl_beads.commands.list_work_items",
        0,
    )
