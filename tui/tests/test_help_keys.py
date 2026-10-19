"""Help and the legends cannot drift apart (#219): every key a screen's legend names is in its
help section, or among the keys that work anywhere."""

import re

import pytest

from lustjinn_tui.builder import PersonaBuilderScreen
from lustjinn_tui.help import SECTIONS
from lustjinn_tui.history import HistoryScreen
from lustjinn_tui.legend import Hint
from lustjinn_tui.library import LibraryScreen
from lustjinn_tui.newstory import NewStoryScreen
from lustjinn_tui.panes import ReviewScreen


def keys(text: str) -> set[str]:
    """The keys a legend or help key names: ``←→`` is two, ``PgUp/PgDn`` two, ``or`` none."""
    spaced = re.sub(r"([←→↑↓])(?=[←→↑↓])", r"\1 ", text)
    return {part for part in re.split(r"[\s/]+", spaced) if part and part != "or"}


def in_help(section: str) -> set[str]:
    found = {s.name: s for s in SECTIONS}
    return {k for name in (section, "Anywhere") for row in found[name].rows for k in keys(row.key)}


@pytest.mark.parametrize(
    ("hints", "section"),
    [
        (LibraryScreen.HINTS, "Library"),
        (LibraryScreen.PIECE_HINTS, "Library"),
        (HistoryScreen.HINTS, "An entry's history"),
        (PersonaBuilderScreen.HINTS, "Persona builder"),
        (NewStoryScreen.HINTS, "New story"),
        (ReviewScreen.HINTS, "Review facts (/review)"),
    ],
)
def test_every_key_in_the_legend_is_in_help(hints: tuple[Hint, ...], section: str) -> None:
    missing = {k for hint in hints for k in keys(hint.key)} - in_help(section)
    assert not missing, f"{section}: the legend names {sorted(missing)} and help does not"


def test_the_keys_are_read_as_the_legend_and_help_write_them() -> None:
    assert keys("←→") == {"←", "→"}
    assert keys("PgUp/PgDn") == {"PgUp", "PgDn"}
    assert keys("Ctrl+R  or  R") == {"Ctrl+R", "R"}
    assert keys("Space  /  Enter") == {"Space", "Enter"}
