import difflib
from pathlib import Path

import black


def test_show_black_diff_for_sync_diagnostic():
    path = Path(__file__).resolve().parents[1] / "src" / "sync" / "sync.py"
    current = path.read_text()
    formatted = black.format_file_contents(
        current,
        fast=False,
        mode=black.FileMode(),
    )
    if current != formatted:
        diff = "".join(
            difflib.unified_diff(
                current.splitlines(keepends=True),
                formatted.splitlines(keepends=True),
                fromfile="current",
                tofile="black",
            )
        )
        raise AssertionError("\n" + diff)
