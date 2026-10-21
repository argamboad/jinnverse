"""Turning the personas already in the library into pieces (#155).

A persona is paragraphs, and the paragraphs follow the skeleton the pieces are slotted by. Each
paragraph is given a slot by simple rules (position and keywords, no model call) and the owner
confirms it; a paragraph becomes a piece, except in the look and personality slots, where the
paragraphs that follow each other become one piece (the look with its style and marks, the
personality with its humour and passions, #254); the persona's own name is replaced by the
placeholders the joiner fills in again; paragraphs several personas share become one piece. A
persona is only saved when its pieces, joined by the joiner, give back its text exactly — that is
the proof the format was not broken — and the persona itself is never touched.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jinnverse.models import Persona, PersonaPiece, PieceSlot, Voice
from jinnverse.persona_pieces import FULL_NAME, SHORT_NAME, SLOT_LABELS, PieceError, assemble

TITLES = frozenset({"professor", "prof.", "dr.", "dr", "mr.", "mrs.", "ms.", "miss", "sir", "lady"})
"""Words a name may start with that are not the name a persona is called by."""

MERGED = frozenset({PieceSlot.LOOK, PieceSlot.PERSONALITY})
"""The slots whose paragraphs, when they follow each other, make one piece."""

# The first rule a paragraph matches decides its slot. The first paragraph is always the look.
RULES: tuple[tuple[PieceSlot, re.Pattern[str]], ...] = (
    (
        PieceSlot.LOOK,  # the marks
        re.compile(r"^(his|her|their)\s+(tattoos?|scars?|piercings?)\b", re.IGNORECASE),
    ),
    (PieceSlot.PERSONALITY, re.compile(r"^(his|her|their)\s+humou?r\b", re.IGNORECASE)),
    (
        PieceSlot.PERSONALITY,  # the passions
        re.compile(r"^(his|her|their)\s+(passions|interests|hobbies)\b", re.IGNORECASE),
    ),
    (
        PieceSlot.HOME,
        re.compile(
            r"\b(lives? in|penthouse|apartment|flat|kitchen|bedroom|rooftop|"
            r"drives an?|rides an?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        PieceSlot.FAMILY,
        re.compile(
            r"\b(son of|daughter of|sister|brother|twin|parents|father|mother|descends from)\b",
            re.IGNORECASE,
        ),
    ),
    (
        PieceSlot.LOOK,  # the style
        re.compile(
            r"\b(dresses|dressed|wardrobe|clothing|clothes|groomed|wears|satchel|backpack)\b",
            re.IGNORECASE,
        ),
    ),
    (
        PieceSlot.PERSONALITY,
        re.compile(
            r"\b(values|dislikes|emotionally mature|exceptionally curious)\b", re.IGNORECASE
        ),
    ),
)


def suggest_slot(text: str, index: int) -> PieceSlot:
    """The slot a paragraph is most likely written for: the look first, then the first rule it
    matches, and the work otherwise (the skeleton's one paragraph with no keyword of its own)."""
    if index == 0:
        return PieceSlot.LOOK
    for slot, rule in RULES:
        if rule.search(text):
            return slot
    return PieceSlot.WORK


def suggest_names(first_paragraph: str) -> tuple[str | None, str | None]:
    """The full name a persona opens with ("Allan Sanlúcar El Kettani is …") and the short one it
    uses after, which is the first word of the name that is not a title."""
    found = re.match(
        r"^(?P<name>(?:(?:Dr|Mr|Mrs|Ms|Prof|Sir)\.\s+)?[^.,;:!?]{2,60}?) (?:is|was) ",
        first_paragraph,
    )
    if found is None:
        return None, None
    full = found["name"].strip()
    words = [word for word in full.split() if word.lower() not in TITLES]
    return full, (words[0] if words else None)


@dataclass
class Paragraph:
    text: str
    slot: PieceSlot


@dataclass
class Plan:
    """One persona, split into paragraphs, with the slot each is suggested for."""

    persona: str
    original: str
    full_name: str | None
    short_name: str | None
    paragraphs: list[Paragraph] = field(default_factory=list[Paragraph])

    def pieces(self) -> list[tuple[PieceSlot, str]]:
        """The (slot, text) of each piece, the persona's name replaced by placeholders: a
        paragraph each, but for the look and the personality, where the paragraphs that follow
        each other are one piece of several paragraphs."""
        pieces: list[tuple[PieceSlot, str]] = []
        for paragraph in self.paragraphs:
            text = self._placeholders(paragraph.text)
            if pieces and paragraph.slot in MERGED and pieces[-1][0] is paragraph.slot:
                pieces[-1] = (paragraph.slot, f"{pieces[-1][1]}\n{text}")
            else:
                pieces.append((paragraph.slot, text))
        return pieces

    def _placeholders(self, text: str) -> str:
        if self.full_name:
            text = text.replace(self.full_name, FULL_NAME)
        if self.short_name:
            text = re.sub(rf"\b{re.escape(self.short_name)}\b", SHORT_NAME, text)
        return text

    def rejoins(self) -> bool:
        """Whether the joiner, given these pieces, gives back the persona's text exactly."""
        try:
            return self._rejoined() == self.original.strip()
        except PieceError:
            return False

    def _rejoined(self) -> str:
        picks: dict[PieceSlot, list[PersonaPiece]] = {}
        for slot, text in self.pieces():
            picks.setdefault(slot, []).append(PersonaPiece(slot=slot, voice=Voice.HE, text=text))
        if self.full_name and self.short_name:
            name = PersonaPiece(
                slot=PieceSlot.NAME, voice=Voice.HE, text=self.full_name, short=self.short_name
            )
            picks[PieceSlot.NAME] = [name]
        return assemble(picks)


def plan_persona(persona: str, text: str) -> Plan:
    """The suggestion for one persona. Blank lines are not paragraphs."""
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    full, short = suggest_names(lines[0]) if lines else (None, None)
    plan = Plan(persona=persona, original=text, full_name=full, short_name=short)
    plan.paragraphs = [Paragraph(line, suggest_slot(line, i)) for i, line in enumerate(lines)]
    return plan


Say = Callable[[str], None]
Ask = Callable[[str], str]


def describe(plan: Plan) -> list[str]:
    """What the owner is shown: the names, then each paragraph with its slot."""
    lines = [
        f"{plan.persona}: name {plan.full_name or '?'} / short {plan.short_name or '?'}",
        *(
            f"  {number:>2}  {paragraph.slot.value:<12} {paragraph.text[:70]}"
            for number, paragraph in enumerate(plan.paragraphs, start=1)
        ),
        "  rejoins exactly" if plan.rejoins() else "  DOES NOT rejoin exactly",
    ]
    return lines


def review(plan: Plan, ask: Ask, say: Say) -> bool:
    """Shows a plan and takes corrections until the owner accepts it or skips it.

    An empty answer accepts, but only a plan that rejoins exactly. `N=slot` changes paragraph N
    (several can be given at once, `4=family 5=work`), `names=Full Name|Short` sets the names,
    `skip` leaves the persona out. Returns whether the plan is to be saved.
    """
    while True:
        for line in describe(plan):
            say(line)
        answer = ask("Enter to accept, N=slot to change, names=Full|Short, skip: ").strip()
        if answer == "":
            if plan.rejoins():
                return True
            say("  This does not rejoin exactly; change a slot or the names, or skip.")
        elif answer.lower() == "skip":
            return False
        else:
            _correct(plan, answer, say)


def _correct(plan: Plan, answer: str, say: Say) -> None:
    if answer.lower().startswith("names="):
        full, _, short = answer[len("names=") :].partition("|")
        plan.full_name = full.strip() or None
        plan.short_name = short.strip() or None
        return
    for change in answer.split():
        number, _, wanted = change.partition("=")
        try:
            paragraph = plan.paragraphs[int(number) - 1]
            paragraph.slot = PieceSlot(wanted.lower())
        except ValueError, IndexError:
            say(f"  '{change}' is not a paragraph number and a slot ({', '.join(PieceSlot)}).")


@dataclass
class Report:
    created: int = 0
    reused: int = 0
    skipped: list[str] = field(default_factory=list[str])
    personas: int = 0


async def save(session: AsyncSession, plans: Sequence[Plan]) -> Report:
    """Creates the pieces of every plan that rejoins exactly. A piece already in the pool (same
    slot, voice and text) is reused, so running it again adds nothing. Writes no persona."""
    report = Report()
    pool = list(await session.scalars(select(PersonaPiece)))
    known = {(p.slot, p.voice, p.text) for p in pool}
    used = {(p.slot, p.voice, p.name.lower()) for p in pool}

    def label(plan: Plan, slot: PieceSlot, preferred: str | None) -> str:
        base = preferred or f"{plan.persona} · {SLOT_LABELS[slot]}"
        name, number = base, 1
        while (slot, Voice.HE, name.lower()) in used:
            number += 1
            name = f"{base} {number}"
        used.add((slot, Voice.HE, name.lower()))
        return name

    for plan in plans:
        if not plan.rejoins():
            report.skipped.append(plan.persona)
            continue
        report.personas += 1
        wanted: list[tuple[PieceSlot, str, str | None, str | None]] = [
            (slot, text, None, None) for slot, text in plan.pieces()
        ]
        if plan.full_name and plan.short_name:
            wanted.insert(0, (PieceSlot.NAME, plan.full_name, plan.short_name, plan.full_name))
        for slot, text, short, name in wanted:
            if (slot, Voice.HE, text) in known:
                report.reused += 1
                continue
            session.add(
                PersonaPiece(
                    slot=slot,
                    voice=Voice.HE,
                    name=label(plan, slot, name),
                    text=text,
                    short=short,
                )
            )
            known.add((slot, Voice.HE, text))
            report.created += 1
    await session.commit()
    return report


async def plans_for_all(session: AsyncSession) -> list[Plan]:
    """A plan for every persona in the library, by name. Reads only."""
    personas = await session.scalars(select(Persona).order_by(Persona.name))
    return [plan_persona(persona.name, persona.text) for persona in personas]
