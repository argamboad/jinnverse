"""Waiting for the app without sleeping.

The screens read and write through Textual workers, so a test that pressed a key waits for the
workers to finish and the messages to be handled — not for a number of seconds that has to be
long enough on the slowest machine and is paid on every machine. ``settle`` is that wait. The
few things a timer brings about (a message leaving the phone's row, the next knock on a
sleeping server) are waited for by polling with ``until``, which returns the moment they happen.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from textual.pilot import Pilot
from textual.worker import Worker, WorkerState

PATIENCE = 10.0
"""Seconds either wait allows before it gives up and says what it was waiting for."""


async def settle(pilot: Pilot[Any]) -> None:
    """Returns once the app is idle: every worker finished and every message handled.

    A worker may start another as it ends (a story's load refreshes the header and the spend),
    so it goes round until a round finds none running. A timer is not a worker and is not
    waited for: that is what ``until`` is for.
    """
    running: list[Worker[Any]] = []
    try:
        async with asyncio.timeout(PATIENCE):
            while True:
                await pilot.pause()
                running = [w for w in pilot.app.workers if w.state is WorkerState.RUNNING]
                if not running:
                    return
                # A cancelled worker (an exclusive one replaced it) or a failed one ends the
                # wait like any other; the app itself reports a failure, as it would in use.
                # Shielded, so that giving up does not cancel the workers themselves.
                await asyncio.shield(
                    asyncio.gather(*(w.wait() for w in running), return_exceptions=True)
                )
    except TimeoutError:
        raise TimeoutError(f"the app did not settle within {PATIENCE}s: {running}") from None


async def until(pilot: Pilot[Any], condition: Callable[[], bool], *, what: str) -> None:
    """Polls ``condition`` between message rounds until it holds, and says ``what`` was waited
    for when it never does."""
    try:
        async with asyncio.timeout(PATIENCE):
            while True:
                await pilot.pause()
                if condition():
                    return
                await asyncio.sleep(0.01)
    except TimeoutError:
        raise TimeoutError(f"waited {PATIENCE}s for {what}") from None
