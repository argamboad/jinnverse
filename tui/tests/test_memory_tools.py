"""The memory tools in the terminal (#235): ``/review`` and ``/condense`` ask first with the
cost, the proposals are kept or dropped one by one, and nothing is applied unasked."""

import uuid
from typing import Any

from textual.pilot import Pilot

from lustjinn_tui.app import LustjinnApp
from lustjinn_tui.confirm import ConfirmScreen
from lustjinn_tui.conversation import ConversationScreen
from lustjinn_tui.panes import ReviewScreen
from lustjinn_tui.stories import StoriesScreen
from tui_support import fake_server as fake

OPENING = '*The door opens.* "You came," she says.'


async def open_story(app: LustjinnApp, pilot: Pilot[None]) -> ConversationScreen:
    await pilot.pause(0.1)
    assert isinstance(app.screen, StoriesScreen)
    await pilot.press("enter")
    await pilot.pause(0.2)
    screen = app.screen
    assert isinstance(screen, ConversationScreen)
    return screen


def fact(subject: str, text: str, *, pinned: bool = False) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "subject": subject,
        "text": text,
        "valid_from_sequence": 1,
        "valid_to_sequence": None,
        "model": None if pinned else "m",
        "pinned": pinned,
        "created_at": "2026-10-19T12:00:00Z",
    }


PLAN = fact("Rowan Hale", "is expected at the dock at dawn.")
KNIFE = fact("Rowan Hale", "carries a knife.")
ROOM = fact("Rowan Hale", "took room seven.")
PAID = fact("Rowan Hale", "paid for a week.")
PROPOSALS: list[dict[str, Any]] = [
    {
        "action": "rewrite",
        "facts": [PLAN],
        "subject": None,
        "text": "went to the dock at dawn.",
        "reason": "The dawn has come.",
    },
    {"action": "retire", "facts": [KNIFE], "subject": None, "text": None, "reason": "Dropped."},
    {
        "action": "merge",
        "facts": [ROOM, PAID],
        "subject": None,
        "text": "took room seven and paid for a week.",
        "reason": "One thing, said twice.",
    },
]


def consequences(app: LustjinnApp) -> str:
    screen = app.screen
    assert isinstance(screen, ConfirmScreen)
    return "\n".join(str(static.render()) for static in screen.query(".consequence"))


def proposals_shown(app: LustjinnApp) -> list[str]:
    screen = app.screen
    assert isinstance(screen, ReviewScreen)
    return [str(static.render()) for static in screen.query(".proposal")]


async def test_review_asks_first_with_the_price_and_esc_calls_nothing(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", OPENING, "I did.", "She smiles.")
    server.proposals[told["id"]] = PROPOSALS
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_story(app, pilot)
        await pilot.press("i", *"/review", "enter")
        await pilot.pause(0.2)

        assert isinstance(app.screen, ConfirmScreen)
        assert "about $0.0031" in consequences(app)
        assert "Nothing changes until you confirm" in consequences(app)
        reviews = [r for r in server.requests if r.url.path.endswith("/facts/review")]
        assert [r.url.params.get("dry_run") for r in reviews] == ["true"]  # the estimate only

        await pilot.press("escape")
        await pilot.pause(0.1)
        assert app.screen is screen
        assert screen.status_line.text == "Cancelled."
        assert len([r for r in server.requests if r.url.path.endswith("/facts/review")]) == 1


async def test_the_proposals_are_listed_and_the_kept_ones_applied_as_one(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", OPENING, "I did.", "She smiles.")
    server.proposals[told["id"]] = PROPOSALS
    async with app.run_test(size=(100, 36)) as pilot:
        screen = await open_story(app, pilot)
        await pilot.press("i", *"/review", "enter")
        await pilot.pause(0.2)
        await pilot.press("enter")  # yes
        await pilot.pause(0.3)

        assert isinstance(app.screen, ReviewScreen)
        shown = proposals_shown(app)
        assert len(shown) == 3
        assert shown[0].startswith("› REWRITE  keep")
        assert "Rowan Hale: is expected at the dock at dawn." in shown[0]
        assert "→ Rowan Hale: went to the dock at dawn." in shown[0]
        assert "The dawn has come." in shown[0]
        assert "MERGE" in shown[2]
        assert "took room seven." in shown[2]
        assert "paid for a week." in shown[2]

        await pilot.press("down", "space")  # drop the retire
        await pilot.pause(0.1)
        shown = proposals_shown(app)
        assert shown[1].startswith("› RETIRE  drop")
        assert shown[0].startswith("  REWRITE  keep")

        await pilot.press("a")
        await pilot.pause(0.3)
        assert app.screen is screen
        [confirmed] = server.applied
        assert [p["action"] for p in confirmed] == ["rewrite", "merge"]
        assert confirmed[0]["fact_ids"] == [PLAN["id"]]
        assert confirmed[1]["fact_ids"] == [ROOM["id"], PAID["id"]]
        assert confirmed[1]["text"] == "took room seven and paid for a week."
        assert screen.status_line.text.startswith(
            "Applied 2 proposal(s): 3 fact(s) retired, 2 added."
        )


async def test_esc_on_the_proposals_applies_nothing(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", OPENING, "I did.", "She smiles.")
    server.proposals[told["id"]] = PROPOSALS
    async with app.run_test(size=(100, 36)) as pilot:
        screen = await open_story(app, pilot)
        await pilot.press("i", *"/review", "enter")
        await pilot.pause(0.2)
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ReviewScreen)

        await pilot.press("escape")
        await pilot.pause(0.1)

        assert app.screen is screen
        assert server.applied == []
        assert not any(r.url.path.endswith("/apply") for r in server.requests)


async def test_a_review_with_nothing_to_propose_says_so(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", OPENING, "I did.", "She smiles.")
    server.proposals[told["id"]] = []
    server.review_estimate = None
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_story(app, pilot)
        await pilot.press("i", *"/review", "enter")
        await pilot.pause(0.2)
        assert "about what a reply costs" in consequences(app)  # nothing priced yet

        await pilot.press("enter")
        await pilot.pause(0.3)

        assert app.screen is screen
        assert screen.status_line.text == "The model proposes no change to the facts."


async def test_condense_asks_with_what_would_merge_and_then_merges(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", OPENING, "I did.", "She smiles.")
    server.summaries[told["id"]] = [(1, 10, 800), (11, 20, 700), (21, 30, 600)]
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_story(app, pilot)
        await pilot.press("i", *"/condense", "enter")
        await pilot.pause(0.2)

        assert isinstance(app.screen, ConfirmScreen)
        text = consequences(app)
        assert "Turns 1 to 20, 1,500 tokens" in text
        assert "The newest summary stays." in text
        assert "about $0.0003" in text

        await pilot.press("enter")
        await pilot.pause(0.3)

        assert app.screen is screen
        assert screen.status_line.text == "2 summaries became one: 1,500 tokens are now 1,058."
        assert server.summaries[told["id"]] == [(1, 20, 1058), (21, 30, 600)]


async def test_condense_takes_a_count_and_refuses_a_bad_one(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", OPENING, "I did.", "She smiles.")
    server.summaries[told["id"]] = [(1, 10, 800), (11, 20, 700), (21, 30, 600)]
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_story(app, pilot)
        await pilot.press("i", *"/condense x", "enter")
        await pilot.pause(0.2)
        assert app.screen is screen
        assert screen.status_line.text.startswith("/condense takes how many")
        assert not any(r.url.path.endswith("/condense") for r in server.requests)

        await pilot.press("i", *"/condense 3", "enter")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ConfirmScreen)
        assert "Merge the oldest 3 summaries into one?" in str(
            app.screen.query_one(".question").render()
        )
        assert "The newest summary stays." not in consequences(app)


async def test_a_story_with_too_few_summaries_is_told_so(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", OPENING, "I did.", "She smiles.")
    server.summaries[told["id"]] = [(1, 10, 800)]
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_story(app, pilot)
        await pilot.press("i", *"/condense", "enter")
        await pilot.pause(0.2)

        assert isinstance(app.screen, ConversationScreen)
        assert screen.status_line.text == "This story has fewer than two summaries to merge."
