"""The status block in the terminal: the screen that switches lines on and off, adds one, pins a
character and corrects a value; the scene line in the conversation's header; and the lines a new
story starts with (#176)."""

from __future__ import annotations

from textual.pilot import Pilot

from lustjinn_tui.api import StatusBlock, StatusField, StatusValue
from lustjinn_tui.app import LustjinnApp
from lustjinn_tui.confirm import ConfirmScreen
from lustjinn_tui.conversation import ConversationScreen
from lustjinn_tui.newstory import NewStoryScreen, Ticks
from lustjinn_tui.status import Kind
from lustjinn_tui.statusblock import (
    StatusBlockScreen,
    build_items,
    in_scene,
    parse_new_field,
    scene_line,
)
from lustjinn_tui.stories import StoriesScreen
from tui_support import fake_server as fake


def field(key: str, label: str, scope: str, position: int, *, on: bool = True) -> StatusField:
    return StatusField(
        key=key,
        label=label,
        icon={"time": "📅", "place": "📍", "outfit": "👗"}.get(key),
        scope=scope,  # type: ignore[arg-type]
        enabled=on,
        position=position,
    )


def value(key: str, who: str, text: str, seen: int, *, by_hand: bool = False) -> StatusValue:
    return StatusValue(field=key, who=who, value=text, seen=seen, by_hand=by_hand)


FIELDS = [
    field("time", "Day and time", "scene", 0),
    field("place", "Place", "scene", 1, on=False),
    field("outfit", "Outfit", "character", 2),
]


# --- the small rules --------------------------------------------------------------------------


def test_what_is_typed_for_a_new_field_says_its_scope_and_its_words() -> None:
    assert parse_new_field("Who she is with") == ("Who she is with", "character", [])
    assert parse_new_field("  Scene: Weather ") == ("Weather", "scene", [])
    assert parse_new_field("Heat = Low, high | Low; Boiling") == (
        "Heat",
        "character",
        ["Low", "high", "Boiling"],
    )
    assert parse_new_field("scene: Weather = rain, sun") == ("Weather", "scene", ["rain", "sun"])
    assert parse_new_field("   ") is None
    assert parse_new_field("scene:") is None
    assert parse_new_field(" = a, b") is None


def test_the_rows_are_fields_then_starters_then_pins_then_what_each_line_holds() -> None:
    block = StatusBlock(
        fields=FIELDS,
        starters=[],
        pins=["Peach"],
        values=[
            value("outfit", "Sammy", "a hoodie", 5),
            value("time", "", "Day 1", 5, by_hand=True),
            value("outfit", "Peach", "a robe", 5),
            value("gone", "Peach", "x", 5),
        ],
    )

    items = build_items(block)

    assert [(i.kind, i.label) for i in items] == [
        ("field", "Day and time"),
        ("field", "Place"),
        ("field", "Outfit"),
        ("pin", "Peach"),
        ("value", "Scene · Day and time"),
        ("value", "Peach · Outfit"),
        ("value", "Sammy · Outfit"),
    ]
    assert [i.on for i in items[:3]] == [True, False, True]
    assert items[4].note == "by hand"


def test_who_is_in_scene_is_pinned_first_then_recent_and_the_scene_line_says_so() -> None:
    block = StatusBlock(
        fields=FIELDS,
        pins=["old friend"],
        values=[
            value("time", "", "Day 1", 30),
            value("outfit", "Peach", "a robe", 30),
            value("outfit", "Sammy", "a hoodie", 18),
            value("outfit", "Stranger", "a coat", 17),
            value("outfit", "Old Friend", "a suit", 2),
        ],
    )

    assert in_scene(block, 30) == ["Old Friend", "Peach", "Sammy"]
    assert scene_line(block, 30) == "📅 Day 1  ·  with Old Friend, Peach, Sammy"
    assert scene_line(StatusBlock(fields=FIELDS), 30) is None


def test_a_scene_field_that_is_off_is_not_in_the_scene_line() -> None:
    block = StatusBlock(fields=FIELDS, values=[value("place", "", "the bar", 3)])

    assert scene_line(block, 3) is None


# --- the screen -------------------------------------------------------------------------------


def block_screen(app: LustjinnApp) -> StatusBlockScreen:
    screen = app.screen
    assert isinstance(screen, StatusBlockScreen)
    return screen


async def open_block(app: LustjinnApp, pilot: Pilot[None]) -> StatusBlockScreen:
    await pilot.pause(0.1)
    assert isinstance(app.screen, StoriesScreen)
    await pilot.press("enter")
    await pilot.pause(0.2)
    assert isinstance(app.screen, ConversationScreen)
    await pilot.press("t")
    await pilot.pause(0.3)
    return block_screen(app)


def adopted(server: fake.FakeServer, story: dict[str, object], *keys: str) -> None:
    block = server.status_blocks.setdefault(
        str(story["id"]), {"fields": [], "values": [], "pins": []}
    )
    for starter in server.status_starters:
        if starter["key"] in keys:
            block["fields"].append(
                {**starter, "words": None, "enabled": True, "position": len(block["fields"])}
            )


async def test_a_story_with_no_lines_offers_the_starters_and_adding_one_switches_it_on(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", "An opening.")
    async with app.run_test(size=(110, 36)) as pilot:
        screen = await open_block(app, pilot)
        assert [(i.kind, i.label) for i in screen.rows.items] == [
            ("starter", "Day and time"),
            ("starter", "Place"),
            ("starter", "Outfit"),
            ("starter", "Mood"),
        ]
        await pilot.press("down", "space")  # Place
        await pilot.pause(0.3)
        assert [f["key"] for f in server.status_blocks[told["id"]]["fields"]] == ["place"]
        first = screen.rows.items[0]
        assert (first.kind, first.label, first.on) == ("field", "Place", True)
        assert screen.status_line.kind == Kind.SUCCESS
        assert screen.status_line.text == "Place added, switched on."


async def test_space_switches_a_line_on_and_off_and_the_server_is_told(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", "An opening.")
    adopted(server, told, "time", "outfit")
    async with app.run_test(size=(110, 36)) as pilot:
        screen = await open_block(app, pilot)
        drawn = screen.rows.render().plain
        assert "▌ [x] 📅 Day and time  scene" in drawn
        assert "[x] 👗 Outfit  each character" in drawn
        await pilot.press("space")
        await pilot.pause(0.3)
        assert "▌ [ ] 📅 Day and time  scene" in screen.rows.render().plain
        assert server.status_blocks[told["id"]]["fields"][0]["enabled"] is False
        assert screen.status_line.text == "Day and time off: from the next reply."
        assert screen.rows.items[0].on is False
        await pilot.press("enter")  # Enter does the same
        await pilot.pause(0.3)
        assert server.status_blocks[told["id"]]["fields"][0]["enabled"] is True


async def test_a_new_field_is_typed_with_its_scope_and_words(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", "An opening.")
    async with app.run_test(size=(110, 36)) as pilot:
        screen = await open_block(app, pilot)
        await pilot.press("a")
        assert screen.legend.text.startswith(" Enter Keep   Esc Cancel")
        await pilot.press(*"Heat = Low, High", "enter")
        await pilot.pause(0.3)
        [heat] = server.status_blocks[told["id"]]["fields"]
        assert (heat["label"], heat["scope"], heat["kind"], heat["words"]) == (
            "Heat",
            "character",
            "words",
            ["Low", "High"],
        )
        assert screen.status_line.text == "Heat added: asked for from the next reply."
        await pilot.press("a", "escape")  # Esc leaves the typing, not the screen
        assert block_screen(app) is screen
        await pilot.press("a", "enter")  # nothing typed
        assert screen.status_line.kind == Kind.WARNING
        assert len(server.status_blocks[told["id"]]["fields"]) == 1


async def test_a_character_is_pinned_and_unpinned(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", "An opening.")
    adopted(server, told, "outfit")
    async with app.run_test(size=(110, 36)) as pilot:
        screen = await open_block(app, pilot)
        await pilot.press("n", *"Peach", "enter")
        await pilot.pause(0.3)
        assert server.status_blocks[told["id"]]["pins"] == ["Peach"]
        pin_index = next(i for i, item in enumerate(screen.rows.items) if item.kind == "pin")
        await pilot.press(*["down"] * pin_index, "delete")
        await pilot.pause(0.3)
        assert server.status_blocks[told["id"]]["pins"] == []
        assert screen.status_line.text == "Unpinned."


async def test_a_value_is_corrected_and_cleared(app: LustjinnApp, server: fake.FakeServer) -> None:
    told = server.add("Tale", "An opening.")
    adopted(server, told, "time", "outfit")
    server.status_blocks[told["id"]]["values"] = [
        {"field": "time", "who": "", "value": "Day 1", "by_hand": False, "seen": 1},
        {"field": "outfit", "who": "Peach", "value": "a robe", "by_hand": False, "seen": 1},
    ]
    async with app.run_test(size=(110, 36)) as pilot:
        screen = await open_block(app, pilot)
        values = [i for i, item in enumerate(screen.rows.items) if item.kind == "value"]
        await pilot.press(*["down"] * values[1], "space")  # Peach · Outfit
        await pilot.press(*"nothing but heels", "enter")  # the field selects the old value
        await pilot.pause(0.3)
        row = {v["field"]: v for v in server.status_blocks[told["id"]]["values"]}
        assert row["outfit"]["value"] == "nothing but heels"
        assert row["outfit"]["by_hand"] is True
        assert [i.note for i in screen.rows.items if i.label == "Peach · Outfit"] == ["by hand"]
        await pilot.press("delete")
        await pilot.pause(0.3)
        assert [v["field"] for v in server.status_blocks[told["id"]]["values"]] == ["time"]
        assert screen.status_line.text == "Cleared."


async def test_deleting_a_field_asks_first_and_takes_what_it_holds(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", "An opening.")
    adopted(server, told, "time", "outfit")
    server.status_blocks[told["id"]]["values"] = [
        {"field": "time", "who": "", "value": "Day 1", "by_hand": False, "seen": 1},
    ]
    async with app.run_test(size=(110, 36)) as pilot:
        screen = await open_block(app, pilot)
        await pilot.press("delete")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("escape")  # anything but Enter leaves everything as it is
        await pilot.pause(0.2)
        assert len(server.status_blocks[told["id"]]["fields"]) == 2
        await pilot.press("delete", "enter")
        await pilot.pause(0.4)
        assert block_screen(app) is screen
        assert [f["key"] for f in server.status_blocks[told["id"]]["fields"]] == ["outfit"]
        assert server.status_blocks[told["id"]]["values"] == []


async def test_a_refusal_is_the_status_row_and_the_list_stays(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    told = server.add("Tale", "An opening.")
    adopted(server, told, "time")
    async with app.run_test(size=(110, 36)) as pilot:
        screen = await open_block(app, pilot)
        before = [i.label for i in screen.rows.items]
        server.status_blocks[told["id"]]["fields"].clear()  # gone elsewhere meanwhile
        await pilot.press("space")
        await pilot.pause(0.3)
        assert screen.status_line.kind == Kind.ERROR
        assert "no such field" in screen.status_line.text
        assert [i.label for i in screen.rows.items] == before  # not redrawn from nothing


# --- the conversation -------------------------------------------------------------------------


async def test_the_header_carries_the_scene_line(app: LustjinnApp, server: fake.FakeServer) -> None:
    told = server.add("Tale", "An opening.", "My turn.", "A reply.")
    adopted(server, told, "time", "outfit")
    server.status_blocks[told["id"]]["values"] = [
        {"field": "time", "who": "", "value": "Day 1, 11:52 PM", "by_hand": False, "seen": 3},
        {"field": "outfit", "who": "Peach", "value": "a robe", "by_hand": False, "seen": 3},
    ]
    async with app.run_test(size=(110, 36)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.4)
        screen = app.screen
        assert isinstance(screen, ConversationScreen)
        assert "📅 Day 1, 11:52 PM  ·  with Peach" in "\n".join(screen._header_lines())  # pyright: ignore[reportPrivateUsage]


async def test_the_conversation_has_a_key_for_the_status_block(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    server.add("Tale", "An opening.")
    async with app.run_test(size=(110, 36)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("enter")
        await pilot.pause(0.3)
        assert ("T", "Status block") in [(h.key, h.label) for h in ConversationScreen.HINTS]
        await pilot.press("t")
        await pilot.pause(0.3)
        assert isinstance(app.screen, StatusBlockScreen)
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ConversationScreen)


# --- a new story ------------------------------------------------------------------------------


def starting_form(server: fake.FakeServer) -> None:
    server.shelve("characters", "Elena", "You are Elena.", opening="*The door opens.*")
    server.default_persona = server.shelve("personas", "Me", "A quiet man.")


async def test_the_new_story_form_offers_the_starters_unticked(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    starting_form(server)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("n")
        await pilot.pause(0.3)
        screen = app.screen
        assert isinstance(screen, NewStoryScreen)
        ticks = screen.query_one("#status-lines", Ticks)
        assert ticks.display
        assert ticks.keys == []
        drawn = ticks.render().plain
        assert "[ ] Day and time" in drawn
        assert "[ ] Mood" in drawn


async def test_ticked_lines_are_adopted_when_the_story_is_created(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    starting_form(server)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("n")
        await pilot.pause(0.3)
        await pilot.press(*"Tale", "tab", "tab", "tab")  # name, character, persona, then the lines
        screen = app.screen
        assert isinstance(screen, NewStoryScreen)
        ticks = screen.query_one("#status-lines", Ticks)
        assert screen.focused is ticks
        await pilot.press("right", "space", "right", "right", "space")  # Place and Mood
        assert ticks.keys == ["place", "mood"]
        drawn = ticks.render().plain
        assert "[ ] Day and time" in drawn
        assert "[x] Place" in drawn
        assert "[x] Mood" in drawn
        await pilot.press("enter")  # the last field creates
        await pilot.pause(0.4)
        assert isinstance(app.screen, ConversationScreen)
        [created] = server.stories
        assert [f["key"] for f in server.status_blocks[created["id"]]["fields"]] == [
            "place",
            "mood",
        ]


async def test_creating_without_ticking_adds_no_lines_and_makes_no_extra_call(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    starting_form(server)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("n")
        await pilot.pause(0.3)
        # The name, the character, the persona, and Enter on the persona creates.
        await pilot.press(*"Tale", "enter", "enter", "enter")
        await pilot.pause(0.4)
        assert isinstance(app.screen, ConversationScreen)
        assert not any("/status/adopt" in r.url.path for r in server.requests)


async def test_the_form_is_as_it_was_when_the_starters_cannot_be_read(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    starting_form(server)
    server.status_starters = []
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("n")
        await pilot.pause(0.3)
        screen = app.screen
        assert isinstance(screen, NewStoryScreen)
        assert not screen.query_one("#status-lines", Ticks).display
