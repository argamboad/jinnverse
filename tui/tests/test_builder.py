"""The persona builder: slots and pieces side by side, a pick, the preview the server joins, a
voice, a new piece written in the editor, and the persona it makes, from the library and from
the new-story form."""

from collections.abc import Callable

from textual.pilot import Pilot

from lustjinn_tui import builder
from lustjinn_tui.app import LustjinnApp
from lustjinn_tui.builder import PersonaBuilderScreen
from lustjinn_tui.confirm import ConfirmScreen
from lustjinn_tui.library import LibraryScreen
from lustjinn_tui.newstory import NewStoryScreen, Panel
from lustjinn_tui.stories import StoriesScreen
from tui_support import fake_server as fake


def pool(server: fake.FakeServer) -> dict[str, dict[str, str]]:
    """A small pool: a name, a look, a home, a vehicle, a pet, and a piece written for her."""
    return {
        "name": server.piece("name", "Allan", "Allan Sanlúcar", short="Allan"),
        "look": server.piece("look", "Athletic", "{name} is an athletic young man."),
        "home": server.piece("home", "Penthouse", "{short} lives in a penthouse."),
        "bike": server.piece("vehicle", "Royal Enfield", "He rides a Royal Enfield."),
        "pet": server.piece("pets", "Lupo", "He has a corgi named Lupo."),
        "hers": server.piece("look", "Her look", "{name} is tall.", voice="she"),
    }


def screen(app: LustjinnApp) -> PersonaBuilderScreen:
    found = app.screen
    assert isinstance(found, PersonaBuilderScreen)
    return found


def preview(app: LustjinnApp) -> str:
    return str(screen(app).query_one("#preview-text").render())


def slot_keys(app: LustjinnApp) -> list[str]:
    return [slot.key for slot in screen(app).slot_rows.items]


def piece_names(app: LustjinnApp) -> list[str]:
    return [piece.name for piece in screen(app).piece_rows.items]


async def open_builder(app: LustjinnApp, pilot: Pilot[None]) -> PersonaBuilderScreen:
    await pilot.pause(0.1)
    assert isinstance(app.screen, StoriesScreen)
    await pilot.press("m")  # the library
    await pilot.pause(0.2)
    assert isinstance(app.screen, LibraryScreen)
    await pilot.press("b")
    await pilot.pause(0.3)
    return screen(app)


async def pick_in(pilot: Pilot[None], slot_downs: int, piece_downs: int = 0) -> None:
    """Moves to a slot, across to its pieces, to one of them, and picks it."""
    await pilot.press(*(["down"] * slot_downs), "right", *(["down"] * piece_downs), "space")
    await pilot.pause(0.2)
    await pilot.press("left")


async def test_b_opens_the_builder_on_the_slots_the_server_lists(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        assert slot_keys(app)[:3] == ["name", "look", "style"]
        assert len(slot_keys(app)) == 12
        assert piece_names(app) == ["Allan"]  # the name slot is selected first
        assert built.legend.text.startswith(" ←→ Slots/pieces")
        assert "pick a piece to see the persona" in preview(app)
        assert "Voice  he" in str(built.query_one("#caption").render())
        assert "GET /persona-pieces" in " ".join(server.paths())


async def test_moving_down_the_slots_shows_the_pieces_written_for_each(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        await open_builder(app, pilot)
        await pilot.press("down")
        await pilot.pause(0.1)
        assert piece_names(app) == ["Athletic"]  # hers is written in another voice: not offered
        await pilot.press("down", "down", "down", "down", "down")
        await pilot.pause(0.1)
        assert screen(app).slot is not None
        assert screen(app).slot.key == "home"  # type: ignore[union-attr]
        assert piece_names(app) == ["Penthouse"]


async def test_space_picks_a_piece_and_the_preview_is_what_the_server_joins(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        await pick_in(pilot, 0)  # the name
        await pick_in(pilot, 1)  # the look
        await pick_in(pilot, 5)  # the home: slots 0 → 6 means five downs from the look
        assert preview(app) == (
            "Allan Sanlúcar is an athletic young man.\nAllan lives in a penthouse."
        )
        assert built.summary() == "3 of 12 slots picked"
        rows = built.slot_rows.render().plain
        assert "✓ Identity and look" in rows
        assert "✓ Home" in rows
        assert "POST /persona-pieces/preview" in " ".join(server.paths())


async def test_space_on_a_picked_piece_takes_it_back(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        await pick_in(pilot, 1)
        await pilot.press("down", "left")  # to the look slot, then the pieces
        await pilot.press("up", "right", "space")
        await pilot.pause(0.2)
        assert built.picks == {}
        assert "pick a piece to see the persona" in preview(app)


async def test_a_pick_the_server_cannot_join_is_explained_in_place_of_the_persona(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        await open_builder(app, pilot)
        await pick_in(pilot, 0)  # a name alone is not a persona
        assert "(Pick at least one piece.)" in preview(app)


async def test_v_changes_the_voice_and_puts_back_pieces_written_in_another(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        await pick_in(pilot, 1)  # the look, in the he voice
        assert len(built.picks["look"]) == 1
        await pilot.press("v")
        await pilot.pause(0.3)
        assert built.voice == "she"
        assert built.picks == {}  # his look is not hers
        assert "Voice  she" in str(built.query_one("#caption").render())
        assert piece_names(app) == ["Her look"]  # still on the look slot
        assert "voice=she" in str([str(r.url) for r in server.requests])


async def test_r_picks_one_piece_for_the_slot_at_random(
    app: LustjinnApp, server: fake.FakeServer, monkeypatch: object
) -> None:
    ids = pool(server)
    server.piece("home", "Loft", "{short} lives in a loft.")
    monkeypatch.setattr(builder, "choose", lambda pieces: pieces[-1])  # type: ignore[attr-defined]
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        await pilot.press("down", "down", "down", "down", "down", "down")  # the home slot
        await pilot.pause(0.1)
        await pilot.press("r")
        await pilot.pause(0.2)
        assert [built.name_of("home", i) for i in built.picks["home"]] == ["Penthouse"]
        assert ids  # the pool was not touched


def caption(app: LustjinnApp) -> str:
    return str(screen(app).query_one("#caption").render())


async def test_the_caption_counts_the_slots_picked_and_the_needed_ones_left(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    """In the web builder's words (#217)."""
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        assert caption(app).startswith("0 of 12 slots picked · 2 needed   Voice  he")
        await pick_in(pilot, 0)  # the name
        assert caption(app).startswith("1 of 12 slots picked · 1 needed")
        await pick_in(pilot, 1)  # the look
        assert caption(app).startswith("2 of 12 slots picked   Voice")
        assert built.summary() == "2 of 12 slots picked"


async def test_f_fills_every_empty_slot_at_random_and_keeps_what_was_picked(
    app: LustjinnApp, server: fake.FakeServer, monkeypatch: object
) -> None:
    pool(server)
    server.piece("home", "Loft", "{short} lives in a loft.")
    server.piece("look", "Lean", "{name} is lean.")
    monkeypatch.setattr(builder, "choose", lambda pieces: pieces[-1])  # type: ignore[attr-defined]
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        await pick_in(pilot, 1)  # the look: Athletic, the first; F must leave it
        await pilot.press("f")
        await pilot.pause(0.3)
        chosen = {slot: [built.name_of(slot, i) for i in ids] for slot, ids in built.picks.items()}
        assert chosen == {
            "name": ["Allan"],
            "look": ["Athletic"],  # picked by hand, kept
            "home": ["Penthouse"],  # the last of Loft and Penthouse, as the fixed choice says
            "vehicle": ["Royal Enfield"],
            "pets": ["Lupo"],
        }  # the slots with no piece in this voice stay empty
        assert built.status_line.text == "Filled 4 empty slots at random."
        assert caption(app).startswith("5 of 12 slots picked   Voice")
        await pilot.press("f")
        await pilot.pause(0.2)
        assert built.status_line.text == (
            "Every slot that has a piece in this voice is picked already."
        )


async def test_n_writes_a_new_piece_in_the_editor_and_picks_it(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    handed: list[str] = []

    def editor(app_: LustjinnApp, text: str, suffix: str) -> str | None:
        handed.append(text)
        return "{name} has dark hair.\n"

    app.editor = editor
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        await pilot.press("down", "n")
        await pilot.pause()
        assert built.legend.text.startswith(" Enter Go on")
        await pilot.press(*"Dark hair", "enter")
        await pilot.pause(0.4)
        assert "identity and look paragraph" in handed[0]
        assert "{name}" in handed[0]
        assert [p["name"] for p in server.pieces if p["slot"] == "look"] == [
            "Athletic",
            "Her look",
            "Dark hair",
        ]
        assert piece_names(app) == ["Athletic", "Dark hair"]
        assert len(built.picks["look"]) == 1
        assert built.status_line.text == "'Dark hair' is in the pool, and picked."


async def test_n_in_the_name_slot_asks_for_the_full_and_the_short_name(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        await pilot.press("n")
        await pilot.pause()
        await pilot.press(*"Owen Quill", "enter")
        await pilot.pause()
        assert "short name" in built.query_one("#field").placeholder  # type: ignore[attr-defined]
        await pilot.press(*"Owen", "enter")
        await pilot.pause(0.4)
        [made] = server.pieces
        assert (made["slot"], made["name"], made["text"], made["short"]) == (
            "name",
            "Owen Quill",
            "Owen Quill",
            "Owen",
        )


async def test_a_piece_whose_editor_text_is_unchanged_is_not_saved(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    app.editor = lambda app_, text, suffix: text
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        await pilot.press("down", "n", *"Nothing", "enter")
        await pilot.pause(0.3)
        assert server.pieces == []
        assert built.status_line.text == "Nothing was written."


async def test_a_name_taken_in_the_pool_is_refused_with_the_servers_sentence(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    app.editor = lambda app_, text, suffix: "He is tall.\n"
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        await pilot.press("down", "n", *"athletic", "enter")
        await pilot.pause(0.4)
        assert "already exists" in built.status_line.text


async def test_ctrl_s_asks_for_the_name_suggested_by_the_pick_and_makes_the_persona(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        await open_builder(app, pilot)
        await pick_in(pilot, 0)
        await pick_in(pilot, 1)
        await pilot.press("ctrl+s")
        await pilot.pause()
        field = screen(app).query_one("#field")
        assert field.value == "allan-sanlucar"  # type: ignore[attr-defined]
        await pilot.press("enter")
        await pilot.pause(0.5)
        # Back on the library, with the new persona on the shelf and selected.
        assert isinstance(app.screen, LibraryScreen)
        assert app.screen.shelf == "personas"
        selected = app.screen.selected
        assert selected is not None
        assert selected.name == "allan-sanlucar"
        [made] = server.library["personas"]
        assert made["text"] == "Allan Sanlúcar is an athletic young man."
        assert app.screen.status_line.text.startswith("Built 'allan-sanlucar' from pieces.")


async def test_a_name_typed_over_the_suggestion_is_the_one_used(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        await open_builder(app, pilot)
        await pick_in(pilot, 0)
        await pick_in(pilot, 1)
        await pilot.press("ctrl+s")
        await pilot.pause()
        field = screen(app).query_one("#field")
        field.value = "allan-roomie"  # type: ignore[attr-defined]
        await pilot.press("enter")
        await pilot.pause(0.5)
        assert [p["name"] for p in server.library["personas"]] == ["allan-roomie"]


async def test_nothing_is_made_from_an_empty_pick(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert built.status_line.text == (
            "A persona needs a name and an identity and look: pick them first."
        )
        assert server.library["personas"] == []


async def test_a_persona_is_not_made_without_its_look_even_with_a_name(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        await pick_in(pilot, 0)
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert built.status_line.text == "A persona needs an identity and look: pick it first."
        rows = built.slot_rows.render().plain
        assert "Identity and look" in rows
        assert "needed" in rows
        assert "Home" in rows
        assert rows.count("needed") == 1  # only the look is still missing
        assert server.library["personas"] == []


async def test_esc_with_nothing_picked_leaves_and_with_a_pick_asks_first(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        await open_builder(app, pilot)
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert isinstance(app.screen, LibraryScreen)
        await pilot.press("b")
        await pilot.pause(0.3)
        await pick_in(pilot, 1)
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("escape")  # anything but Enter says no
        await pilot.pause(0.1)
        assert isinstance(app.screen, PersonaBuilderScreen)
        assert screen(app).picks  # the pick is still there


async def test_the_new_story_form_builds_a_persona_and_picks_it(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    server.shelve("characters", "Elena", "You are Elena.")
    server.shelve("personas", "Me", "A tall man.")
    pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("n")  # a new story
        await pilot.pause(0.3)
        form = app.screen
        assert isinstance(form, NewStoryScreen)
        await pilot.press("ctrl+b")
        await pilot.pause(0.3)
        await pick_in(pilot, 0)  # the name
        await pick_in(pilot, 1)  # the look
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause(0.6)
        assert app.screen is form
        assert [p["name"] for p in server.library["personas"]] == ["Me", "allan-sanlucar"]
        assert form.persona is not None
        assert form.persona.name == "allan-sanlucar"
        assert form.query_one("#persona-text", Panel).text == (
            "Allan Sanlúcar is an athletic young man."
        )
        assert form.status_line.text == "Built 'allan-sanlucar' and picked it."


async def test_the_builder_survives_a_pool_with_nothing_in_a_slot(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    async with app.run_test(size=(110, 40)) as pilot:
        built = await open_builder(app, pilot)
        await pilot.press("down")
        await pilot.pause(0.1)
        assert piece_names(app) == []
        assert "N writes the first one" in built.piece_rows.render().plain
        await pilot.press("r")
        await pilot.pause(0.1)
        assert "no identity and look piece to pick yet" in built.status_line.text


def scripted(replies: list[str | None]) -> Callable[..., str | None]:
    def edit(app: LustjinnApp, text: str, suffix: str) -> str | None:
        return replies.pop(0) if replies else None

    return edit
