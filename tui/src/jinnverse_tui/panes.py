"""Two screens the composer's commands open.

``TextPaneScreen`` (``Views/TextPaneView.cs``) is a page of text, scrolled and then dismissed:
the card, the persona, the facts, the meters, the audit, the cost and the command list are
seven unrelated things that are all, on screen, a body of text too long for the status row and
not worth a screen of its own. It holds a copy of its lines rather than a callback that produces
them: these are answers to "what is true right now", and right now was when the command was
typed.

``AskScreen`` (``Views/AskView.cs``) is the answer to a question asked out of character, and the
one decision it needs. The answer is not in the story and never will be, which is what makes
it safe to ask anything — and dangerous in one way: a model asked something the story never
settled answers confidently rather than saying so, and three turns later the story contradicts a
detail nothing recorded. So the pane offers exactly one thing: ``F`` pins the answer as a fact
the next prompt carries and the extractor cannot retire; anything else closes the pane and the
answer is gone.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.content import Content
from textual.widgets import Static

from jinnverse_tui.api import Aside, Proposal, Reviewed
from jinnverse_tui.commands import Report
from jinnverse_tui.hairline import Hairline
from jinnverse_tui.legend import Hint
from jinnverse_tui.status import Kind
from jinnverse_tui.theme import HEADING
from jinnverse_tui.view import View

SCROLL_HINTS: tuple[Hint, ...] = (Hint("↑↓ PgUp PgDn", "Scroll"), Hint("Esc", "Close"))
SCROLL_BINDINGS: list[BindingType] = [
    Binding("up", "scroll(-1)", "Up", show=False),
    Binding("down", "scroll(1)", "Down", show=False),
    Binding("pageup", "scroll_page(-1)", "Page up", show=False),
    Binding("pagedown", "scroll_page(1)", "Page down", show=False),
    Binding("home", "scroll_home", "Top", show=False),
    Binding("end", "scroll_end", "Bottom", show=False),
]


class Scrolled(View):
    """A view whose body scrolls under the keys, without taking the focus from the screen."""

    BINDINGS: ClassVar[list[BindingType]] = SCROLL_BINDINGS
    AUTO_FOCUS: ClassVar[str | None] = ""

    @property
    def scroller(self) -> VerticalScroll:
        return self.query_one(VerticalScroll)

    def action_scroll(self, direction: int) -> None:
        self.scroller.scroll_relative(y=direction, animate=False)

    def action_scroll_page(self, direction: int) -> None:
        if direction > 0:
            self.scroller.scroll_page_down(animate=False)
        else:
            self.scroller.scroll_page_up(animate=False)

    def action_scroll_home(self) -> None:
        self.scroller.scroll_home(animate=False)

    def action_scroll_end(self) -> None:
        self.scroller.scroll_end(animate=False)


class TextPaneScreen(Scrolled):
    HINTS: ClassVar[tuple[Hint, ...]] = SCROLL_HINTS

    DEFAULT_CSS = """
    TextPaneScreen #body { padding: 0 2; }
    TextPaneScreen .heading { margin-top: 1; }
    TextPaneScreen VerticalScroll { height: 1fr; }
    TextPaneScreen .line { padding-left: 2; }
    """

    def __init__(self, report: Report) -> None:
        super().__init__()
        self.report = report
        self.title = report.title

    def body(self) -> ComposeResult:
        title = Content(self.report.title).markup
        subtitle = Content(self.report.subtitle).markup
        yield Static(
            Content.from_markup(f"{HEADING}{title}[/]   [$muted]{subtitle}[/]"), classes="heading"
        )
        yield Hairline()
        with VerticalScroll():
            yield Static("\n".join(self.report.lines), classes="line")

    @property
    def lines(self) -> Sequence[str]:
        return self.report.lines


class AskScreen(Scrolled):
    TITLE = "Asked"
    HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("F", "Pin as a fact"),
        Hint("↑↓ PgUp PgDn", "Scroll"),
        Hint("Esc", "Discard"),
    )
    PINNED_HINTS: ClassVar[tuple[Hint, ...]] = SCROLL_HINTS
    BINDINGS: ClassVar[list[BindingType]] = [
        *SCROLL_BINDINGS,
        Binding("f,F", "pin", "Pin as a fact", show=False),
    ]

    DEFAULT_CSS = """
    AskScreen #body { padding: 0 2; }
    AskScreen .heading { margin-top: 1; }
    AskScreen VerticalScroll { height: 1fr; }
    AskScreen .question { color: $accent; padding-left: 2; margin-bottom: 1; }
    AskScreen .answer { padding-left: 2; }
    AskScreen #foot { height: 1; }
    """

    def __init__(self, story_id: uuid.UUID, subject: str, aside: Aside) -> None:
        super().__init__()
        self.story_id = story_id
        self.subject = subject
        self.aside = aside
        self.pinned = False

    def hints(self) -> Sequence[Hint]:
        return self.PINNED_HINTS if self.pinned else self.HINTS

    def body(self) -> ComposeResult:
        yield Static(
            Content.from_markup(
                f"{HEADING}Out of character[/]   "
                "[$muted]not in the transcript, not in any later prompt[/]"
            ),
            classes="heading",
        )
        yield Hairline()
        with VerticalScroll():
            yield Static(self.aside.question, classes="question")
            yield Static(self.aside.answer, classes="answer")
        yield Hairline()
        yield Static(self._foot(), id="foot")

    def _foot(self) -> Content:
        if self.pinned:
            return Content.from_markup(
                "  [$success]Pinned. It is in the world layer from the next turn on.[/]"
            )
        model = Content(self.aside.model or "the model").markup
        return Content.from_markup(
            f"  [$muted]answered by {model}   F pins this as a fact · Esc discards it[/]"
        )

    async def action_pin(self) -> None:
        if self.pinned:
            self.status("Already pinned.")
            return
        text = self.aside.answer.strip()
        if not text:
            self.status("There is nothing to pin.", Kind.WARNING)
            return
        pinned = await self.jinnverse.call(
            "Pinning", self.jinnverse.api.add_fact(self.story_id, self.subject, text)
        )
        if pinned is None:
            return
        self.pinned = True
        self.query_one("#foot", Static).update(self._foot())
        self.refresh_hints()
        self.status(
            f"Pinned under {self.subject}. The extractor cannot retire it; /facts shows it.",
            Kind.SUCCESS,
        )


class ReviewScreen(Scrolled):
    """What a fact review proposes (#235): each proposal with the facts it touches, what they
    become and the model's reason, kept until the reader drops it. ``A`` applies the kept ones
    as one; ``Esc`` applies none. The reasons are there to be judged: a review of a real story
    once proposed retiring "owns a custom Telecaster" because the story showed it."""

    TITLE = "Review facts"
    HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("↑↓", "Choose"),
        Hint("Space", "Keep / drop"),
        Hint("A", "Apply the kept"),
        Hint("PgUp PgDn", "Scroll"),
        Hint("Esc", "Discard"),
    )
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", "Up", show=False),
        Binding("down", "move(1)", "Down", show=False),
        Binding("pageup", "scroll_page(-1)", "Page up", show=False),
        Binding("pagedown", "scroll_page(1)", "Page down", show=False),
        Binding("home", "scroll_home", "Top", show=False),
        Binding("end", "scroll_end", "Bottom", show=False),
        Binding("space", "keep_or_drop", "Keep / drop", show=False),
        Binding("a,A", "apply", "Apply", show=False),
    ]

    DEFAULT_CSS = """
    ReviewScreen #body { padding: 0 2; }
    ReviewScreen .heading { margin-top: 1; }
    ReviewScreen VerticalScroll { height: 1fr; }
    ReviewScreen .proposal { padding: 0 2; margin-bottom: 1; }
    ReviewScreen #foot { height: 1; }
    """

    def __init__(
        self,
        story_id: uuid.UUID,
        reviewed: Reviewed,
        applied: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self.story_id = story_id
        self.reviewed = reviewed
        self.proposals: list[Proposal] = list(reviewed.proposals)
        self.kept = [True] * len(self.proposals)
        self.cursor = 0
        self._applied = applied
        self._done = False

    def body(self) -> ComposeResult:
        count = len(self.proposals)
        cost = f"${self.reviewed.cost:.4f}" if self.reviewed.cost is not None else "unpriced"
        skipped = f" · {self.reviewed.skipped} not shown" if self.reviewed.skipped else ""
        yield Static(
            Content.from_markup(
                f"{HEADING}What the model proposes[/]   "
                f"[$muted]{count} proposal(s) · {cost}{skipped}[/]"
            ),
            classes="heading",
        )
        yield Hairline()
        with VerticalScroll():
            for i in range(count):
                yield Static(self._line(i), id=f"proposal-{i}", classes="proposal")
        yield Hairline()
        yield Static(self._foot(), id="foot")

    def _line(self, i: int) -> Content:
        proposal = self.proposals[i]
        mark = "[$accent]›[/]" if i == self.cursor else " "
        state = "[$success]keep[/]" if self.kept[i] else "[$muted]drop[/]"
        lines = [f"{mark} [$accent]{proposal.action.upper()}[/]  {state}"]
        for fact in proposal.facts:
            was = Content(f"{fact.subject}: {fact.text}").markup
            lines.append(f"    [$muted]{was}[/]")
        if proposal.text:
            subject = proposal.subject or (proposal.facts[0].subject if proposal.facts else "")
            now = Content(f"{subject}: {proposal.text}".lstrip(": ")).markup
            lines.append(f"    → {now}")
        if proposal.reason:
            lines.append(f"    [$muted]{Content(proposal.reason).markup}[/]")
        return Content.from_markup("\n".join(lines))

    def _foot(self) -> Content:
        kept = sum(self.kept)
        return Content.from_markup(
            f"  [$muted]{kept} of {len(self.kept)} kept   A applies them · Esc discards all · "
            "pinned facts are never touched[/]"
        )

    def _redraw(self, *indexes: int) -> None:
        for i in indexes:
            if 0 <= i < len(self.proposals):
                self.query_one(f"#proposal-{i}", Static).update(self._line(i))
        self.query_one("#foot", Static).update(self._foot())

    def action_move(self, direction: int) -> None:
        if not self.proposals:
            return
        was = self.cursor
        self.cursor = max(0, min(len(self.proposals) - 1, self.cursor + direction))
        self._redraw(was, self.cursor)
        self.scroller.scroll_to_widget(
            self.query_one(f"#proposal-{self.cursor}", Static), animate=False
        )

    def action_keep_or_drop(self) -> None:
        # Not `action_toggle`: Textual's DOMNode already has one, with another signature.
        if not self.proposals:
            return
        self.kept[self.cursor] = not self.kept[self.cursor]
        self._redraw(self.cursor)

    async def action_apply(self) -> None:
        if self._done:
            return
        confirmed = [p for p, keep in zip(self.proposals, self.kept, strict=True) if keep]
        if not confirmed:
            self.status("Nothing is kept; Esc discards them all.", Kind.WARNING)
            return
        applied = await self.jinnverse.call(
            "Applying", self.jinnverse.api.apply_review(self.story_id, confirmed)
        )
        if applied is None:
            return
        self._done = True
        app = self.jinnverse
        below = app.screen_stack[-2]
        app.pop_screen()
        if isinstance(below, View):
            below.status(
                f"Applied {len(confirmed)} proposal(s): {applied.retired} fact(s) retired, "
                f"{applied.added} added. /facts shows them.",
                Kind.SUCCESS,
            )
        if self._applied is not None:
            await self._applied()
