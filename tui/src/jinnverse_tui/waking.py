"""The waiting state: the API on Render's free tier sleeps and takes up to a minute to wake.

The client knocks on ``/health`` with the wait growing from two to six seconds, the spinner in the
status row the whole time; after two minutes it says so more plainly and offers ``Enter`` to try
again now. Nothing else is reachable until something answers.
"""

from __future__ import annotations

import asyncio
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.widgets import Static

from jinnverse_tui.api import InterceptedError, UnreachableError
from jinnverse_tui.legend import Hint
from jinnverse_tui.view import View


class WakingScreen(View):
    TITLE = "Waking the server"
    HINTS: ClassVar[tuple[Hint, ...]] = (Hint("Enter", "Try again now"), Hint("Q", "Quit"))
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "try_now", "Try again now", show=False),
    ]

    WAITS: ClassVar[tuple[float, ...]] = (2.0, 3.0, 4.0, 5.0, 6.0)
    PLAINER_AFTER: ClassVar[float] = 120.0

    DEFAULT_CSS = """
    WakingScreen #body { padding: 2 4; }
    WakingScreen .lamp { color: $accent; }
    WakingScreen .why { color: $muted; margin-top: 1; }
    WakingScreen .elapsed { color: $warning; margin-top: 1; }
    """

    def __init__(self, note: str | None = None) -> None:
        super().__init__()
        self._note = note
        self._elapsed = 0.0
        self._attempts = 0
        self._intercepted = False
        self._now = asyncio.Event()

    def body(self) -> ComposeResult:
        yield Static("Waking the server…", classes="lamp", id="lamp")
        yield Static(
            self._note
            or f"{self.jinnverse.api.server} is not answering yet. On the free tier the first "
            "call after a quiet spell takes up to a minute.",
            classes="why",
            id="why",
        )
        yield Static("", classes="elapsed", id="elapsed")

    def on_mount(self) -> None:
        self.status_line.busy("Waking the server")
        self.run_worker(self._knock, exclusive=True)  # the method, not a coroutine (chapter 9)

    async def _knock(self) -> None:
        """Knocks until the server answers. The loop outlives an ``await`` that the app may
        close during, so after each one it stops if the app is closing, and it only draws on
        lines that are still there (#222): Textual removes a screen's widgets before it cancels
        the screen's worker, and a knock can wake between the two."""
        waits = self.jinnverse.wake_waits
        while True:
            self._attempts += 1
            try:
                await self.jinnverse.api.health()
            except InterceptedError as intercepted:
                self._intercepted = True
                self._draw("#lamp", "The connection was intercepted.")
                self._draw("#why", str(intercepted))
            except UnreachableError:
                pass
            else:
                if self.is_attached:
                    self.status_line.idle()
                    self.jinnverse.woke()
                return
            if not self.is_attached:
                return
            wait = waits[min(self._attempts - 1, len(waits) - 1)]
            self._now.clear()
            try:
                await asyncio.wait_for(self._now.wait(), wait)
            except TimeoutError:
                self._elapsed += wait
            if not self.is_attached:
                return
            self._show_elapsed()

    def _draw(self, selector: str, text: str) -> None:
        """Updates a line of the lamp if it is still on the screen; a removed one is skipped."""
        for line in self.query(selector).results(Static):
            line.update(text)

    def _show_elapsed(self) -> None:
        if self._elapsed >= self.PLAINER_AFTER and not self._intercepted:
            self._draw("#lamp", "The server has not answered.")
            self._draw(
                "#why",
                "It may be down rather than asleep. Enter tries again now; Q leaves it for later.",
            )
        self._draw(
            "#elapsed",
            f"{self._elapsed:.0f}s · {self._attempts} attempt{'s' if self._attempts != 1 else ''}",
        )

    def action_try_now(self) -> None:
        self._now.set()

    def action_back(self) -> None:
        self.jinnverse.exit()
