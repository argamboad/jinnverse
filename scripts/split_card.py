"""Splits a character's card into a lorebook character: a second character whose card keeps what
every scene needs and whose entries hold the rest (#274).

    uv run python scripts/split_card.py "Blake Jameson University" "BJU · Lorebook" \\
        --keep "THE CAMPUS" --keep "THE CLUBS" --keys bju-keys.json --dry-run

The card is read in the house shape: `=== THE WORLD ===` with upper-case sub-sections
(`THE DORMS`, `DINING`), and `=== THE CAST ===` (or `=== THE CHARACTERS ===`) with one block per
person headed `Name — age, role` or `NAME — role`. What happens:

- the text before the first sub-section stays in the card; each sub-section becomes an entry
  unless `--keep` names it;
- every sheet of the cast becomes an entry, and a one-line roster — the header lines — takes
  the cast's place in the card;
- every other `=== SECTION ===` stays as it is;
- an entry is keyed on the names it is about: for a sheet, the full name, the first and last
  names and any nickname; for a sub-section, its heading's words and the name each of its lines
  or paragraphs opens with. `--keys` is a JSON file with `{"extra": {"Entry name": ["lunch"]},
  "drop": ["rose"]}` for the words only a person can choose, and the ones prose uses.

The original character is not touched. `--dry-run` prints the plan, with tiktoken's figures,
and writes nothing. The database is whichever the environment names, so
`uv run --env-file .env.staging python scripts/split_card.py …` runs it on Neon.
"""

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jinnverse import tokens
from jinnverse.db import dispose_engine, get_sessionmaker
from jinnverse.lore import clean_keys
from jinnverse.models import Character, LibraryHistory, LibraryKind, LoreEntry

SECTION = re.compile(r"^=== (.+) ===$")
SUBSECTION = re.compile(r"^[A-Z][A-Z0-9 ,'&/-]{2,}$")
"""An upper-case heading on a line of its own inside the world: `THE DORMS`, `DINING`."""
SHEET = re.compile(r"^(?P<name>[A-Z][^—\n]*?) — (?P<rest>.+)$")
"""The first line of a person's sheet: the name, a dash, then the age and the role."""
CAST_SECTIONS = ("THE CAST", "THE CHARACTERS")
TITLES = ("Dr. ", "Dr ", "Lieutenant ", "Captain ", "Brother ", "Sister ", "Professor ", "Coach ")
STOPWORDS = {
    "the",
    "of",
    "by",
    "day",
    "and",
    "a",
    "an",
    "on",
    "off",
    "map",
    "hours",
    "there",
    "these",
    "those",
    "this",
    "that",
    "when",
    "says",
    "tells",
    "her",
    "his",
    "she",
    "he",
    "it",
    "no",
    "recurring",
    "men's",
    "women's",
}
NAME_WORDS = {"de", "la", "del", "von", "van", "of", "called", "the"}
"""The lower-case words a name may hold between its capitals: `Maria de la Cruz`, `MAGS`."""
ROSTER_NOTE = "One line each. A character's full sheet is given to you while they are in the scene."


@dataclass
class Entry:
    name: str
    keys: list[str]
    text: str

    def tokens(self) -> int:
        return tokens.for_message(self.text)


@dataclass
class Plan:
    card: str
    entries: list[Entry] = field(default_factory=list[Entry])


@dataclass(frozen=True)
class Extras:
    extra: dict[str, list[str]]
    drop: set[str]

    @classmethod
    def read(cls, path: Path | None) -> Extras:
        if path is None:
            return cls({}, set())
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            {str(k): [str(x) for x in v] for k, v in data.get("extra", {}).items()},
            {str(x).casefold() for x in data.get("drop", [])},
        )


# -- reading the card ------------------------------------------------------------------------------


def sections(card: str) -> list[tuple[str | None, list[str]]]:
    """The card as (section name, its lines), the preamble under None. The heading line is
    not among a section's lines."""
    found: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in card.split("\n"):
        m = SECTION.match(line.strip())
        if m:
            found.append((m.group(1).strip(), []))
        else:
            found[-1][1].append(line)
    return found


def subsections(lines: Sequence[str]) -> list[tuple[str | None, list[str]]]:
    """A section's lines as (sub-section heading, its lines), the lead-in under None."""
    found: list[tuple[str | None, list[str]]] = [(None, [])]
    for i, line in enumerate(lines):
        bare = line.strip()
        starts_paragraph = i == 0 or not lines[i - 1].strip()
        if bare and starts_paragraph and SUBSECTION.match(bare) and not bare.endswith("."):
            found.append((bare, []))
        else:
            found[-1][1].append(line)
    return found


def looks_like_name(text: str) -> bool:
    """Whether the part before the dash is a person's name and not a line of their sheet that
    happens to hold one: `Lieutenant Alexis Tromblay` is, `Says: "I'm not in a rush` is not."""
    if ":" in text or text.count('"') not in (0, 2) or len(text.split()) > 6:
        return False
    words = text.replace(",", "").replace('"', "").split()
    return bool(words) and all(w[0].isupper() or w.lower() in NAME_WORDS for w in words)


def sheet_header(line: str) -> str | None:
    """The name a sheet's first line opens with, or None for any other line."""
    m = SHEET.match(line.strip())
    if m is None or not looks_like_name(m.group("name").strip()):
        return None
    return m.group("name").strip()


def sheets(lines: Sequence[str]) -> list[tuple[str, str, str]]:
    """The cast as (name, header line, whole sheet), each sheet from its header to the next."""
    starts = [
        i
        for i, line in enumerate(lines)
        if sheet_header(line) is not None and (i == 0 or not lines[i - 1].strip())
    ]
    found: list[tuple[str, str, str]] = []
    for n, i in enumerate(starts):
        j = starts[n + 1] if n + 1 < len(starts) else len(lines)
        header = lines[i].strip()
        name = sheet_header(header)
        assert name is not None
        found.append((name, header, "\n".join(lines[i:j]).strip()))
    return found


# -- keys ----------------------------------------------------------------------------------------


def name_keys(name: str) -> list[str]:
    """What a person is called: the full name without title or nickname, each nickname, the
    first name and the last. `MARGUERITE OYELARAN, called MAGS` and `Samantha "Sammy" Jones`
    both give their nickname."""
    keys: list[str] = []
    nicks = re.findall(r'"([^"]+)"', name) + re.findall(r",? called (\w+)", name)
    bare = re.sub(r'\s*"[^"]+"\s*', " ", name)
    bare = re.sub(r",? called \w+", "", bare)
    for title in TITLES:
        bare = bare.removeprefix(title)
    bare = " ".join(bare.split())
    keys.append(bare)
    keys.extend(nicks)
    words = [w for w in bare.replace(",", "").split() if w.lower() not in {"de", "la", "of"}]
    if words:
        keys.append(words[0])
        if len(words) > 1:
            keys.append(words[-1])
    return clean_keys(keys)


OPENER = re.compile(r"^(?P<name>[A-Z][\w'.&-]*(?: [A-Z0-9][\w'.&-]*)*)")
"""A name at the start of a line: `Another Cup`, `Aniston Hall`, `Men's volleyball`."""


def heading_keys(heading: str, lines: Sequence[str]) -> list[str]:
    """What a sub-section is about: the heading's words, and the names its lines open with —
    the part before the dash of a dash entry (`Another Cup — a coffee chain`, `Men's volleyball
    — Monday to Friday`), or the capitalised name a paragraph starts with (`Aniston Hall is the
    coed dormitory`)."""
    keys = [w for w in re.split(r"[ ,/&]+", heading.lower()) if w and w not in STOPWORDS]
    keys.append(heading.lower().removeprefix("the ").strip())
    for i, line in enumerate(lines):
        bare = line.strip()
        if not bare:
            continue
        opener: str | None = None
        if " — " in bare:
            before = bare.split(" — ", 1)[0].strip()
            if 1 <= len(before.split()) <= 4 and ":" not in before and before[0].isupper():
                opener = before
        elif i == 0 or not lines[i - 1].strip():
            m = OPENER.match(bare)
            if m is not None and len(m.group("name").split()) >= 2:
                opener = m.group("name")
        if opener is None:
            continue
        for title in TITLES:
            opener = opener.removeprefix(title)
        if len(opener) < 3 or opener.lower() in STOPWORDS:
            continue
        keys.append(opener)
        if opener.lower().startswith("the "):
            keys.append(opener[4:])
    return clean_keys(keys)


# -- the plan --------------------------------------------------------------------------------------


def plan(card: str, keep: Sequence[str], extras: Extras) -> Plan:
    """The split: the card that stays and the entries that leave it. Pure: nothing is read or
    written here, so the dummy card can be split in a test."""
    kept_names = {k.strip().upper() for k in keep}
    entries: list[Entry] = []
    out: list[str] = []

    def entry(name: str, keys: Sequence[str], text: str) -> None:
        wanted = [*keys, *extras.extra.get(name, [])]
        entries.append(Entry(name, [k for k in clean_keys(wanted) if k not in extras.drop], text))

    for name, lines in sections(card):
        if name is not None:
            out.append(f"=== {name} ===")
        if name == "THE WORLD":
            for heading, body in subsections(lines):
                if heading is None or heading in kept_names:
                    out.extend([heading] if heading else [])
                    out.extend(body)
                else:
                    text = "\n".join([heading, *body]).strip()
                    entry(
                        heading.title() if heading.isupper() else heading,
                        heading_keys(heading, body),
                        text,
                    )
                    if out and out[-1].strip():
                        out.append("")
        elif name in CAST_SECTIONS:
            people = sheets(lines)
            lead_in = (
                lines[: lines.index(next(line for line in lines if SHEET.match(line.strip())))]
                if people
                else lines
            )
            out.extend(lead_in if any(line.strip() for line in lead_in) else [""])
            if people:
                out.extend([ROSTER_NOTE, ""])
                for person, header, text in people:
                    entry(person, name_keys(person), text)
                    out.append(header)
                out.append("")
        else:
            out.extend(lines)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"
    return Plan(text, entries)


def describe(original: str, made: Plan) -> str:
    before = tokens.for_message(original)
    after = tokens.for_message(made.card)
    lines = [
        f"card: {before} tokens -> {after} tokens",
        f"entries: {len(made.entries)}, {sum(e.tokens() for e in made.entries)} tokens in all",
    ]
    for e in made.entries:
        lines.append(f"  {e.tokens():5d}  {e.name}  <- {', '.join(e.keys)}")
    return "\n".join(lines)


# -- writing --------------------------------------------------------------------------------------


async def character_named(session: AsyncSession, name: str) -> Character | None:
    return await session.scalar(select(Character).where(func.lower(Character.name) == name.lower()))


async def write(
    session: AsyncSession, source: Character, name: str, made: Plan, description: str | None
) -> Character:
    """The new character and its entries, each with its first history row, in one transaction.
    Refused when the name is taken: the split never replaces a character."""
    if await character_named(session, name) is not None:
        raise SystemExit(f"A character called '{name}' already exists. Pick another name.")
    character = Character(
        name=name, card=made.card, opening=source.opening, description=description
    )
    session.add(character)
    await session.flush()
    session.add(
        LibraryHistory(
            kind=LibraryKind.CHARACTER,
            entry_id=character.id,
            version=1,
            name=name,
            text=made.card,
            opening=source.opening,
            description=description,
        )
    )
    for e in made.entries:
        row = LoreEntry(character_id=character.id, name=e.name, keys=e.keys, text=e.text)
        session.add(row)
        await session.flush()
        session.add(
            LibraryHistory(
                kind=LibraryKind.LORE, entry_id=row.id, version=1, name=e.name, text=e.text
            )
        )
    await session.commit()
    return character


async def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("character", help="the name of the character to split (not changed)")
    parser.add_argument("new_name", help="the name of the lorebook character to make")
    parser.add_argument(
        "--keep",
        action="append",
        default=[],
        help="a world sub-section that stays in the card; repeatable",
    )
    parser.add_argument(
        "--keys", type=Path, help='a JSON file: {"extra": {entry: [keys]}, "drop": [keys]}'
    )
    parser.add_argument("--description", help="the new character's note for the lists")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and write nothing")
    args = parser.parse_args(argv)
    extras = Extras.read(args.keys)
    async with get_sessionmaker()() as session:
        source = await character_named(session, args.character)
        if source is None:
            print(f"There is no character called '{args.character}'.", file=sys.stderr)
            return 1
        made = plan(source.card, args.keep, extras)
        print(describe(source.card, made))
        if not made.entries:
            print("Nothing to move out: the card has no cast sheets and no world sub-section.")
            return 1
        if args.dry_run:
            print("(dry run: nothing written)")
            return 0
        description = args.description or f"{source.name}, split into a card and lore entries."
        character = await write(session, source, args.new_name, made, description[:200])
        print(f"made  {character.name}  {character.id}  with {len(made.entries)} entries")
    await dispose_engine()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
