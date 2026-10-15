"""The status blocks' API and the /status command (#173)."""

import httpx2
from sqlalchemy.ext.asyncio import AsyncSession

from lustjinn import blocks
from lustjinn.status_api import split_command
from tests.scripted_model import ScriptedModel
from tests.streaming import send, stream
from tests.test_status_reading import a_story_with_fields
from tests.test_turns import a_played_story

MISSING = "01a10d31-0000-7000-8000-000000000000"


def url(story: object, path: str = "") -> str:
    return f"/stories/{story}/status{path}"


async def adopted(client: httpx2.AsyncClient, story: object, *keys: str) -> dict[str, object]:
    response = await client.post(url(story, "/adopt"), json={"keys": list(keys)})
    assert response.status_code == 200, response.text
    return response.json()


# --- reading and adopting ---------------------------------------------------------------------


async def test_a_new_story_has_no_fields_and_is_offered_the_starters(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)

    response = await client.get(url(story.id))

    assert response.status_code == 200
    body = response.json()
    assert (body["fields"], body["values"], body["pins"]) == ([], [], [])
    assert [s["key"] for s in body["starters"]] == ["time", "place", "outfit", "mood"]
    assert body["starters"][2] == {
        "key": "outfit",
        "label": "Outfit",
        "icon": "👗",
        "hint": "what they are wearing now, briefly",
        "kind": "text",
        "scope": "character",
    }


async def test_adopting_moves_a_starter_into_the_story_s_fields(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)

    body = await adopted(client, story.id, "place", "mood")

    assert [f["key"] for f in body["fields"]] == ["place", "mood"]  # type: ignore[index]
    assert [s["key"] for s in body["starters"]] == ["time", "outfit"]  # type: ignore[index]
    assert all(f["enabled"] for f in body["fields"])  # type: ignore[index]


async def test_a_key_that_is_not_a_starter_is_refused_and_nothing_is_adopted(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)

    response = await client.post(url(story.id, "/adopt"), json={"keys": ["place", "pose"]})

    assert response.status_code == 422
    assert "pose" in response.json()["detail"]
    assert (await client.get(url(story.id))).json()["fields"] == []


async def test_a_missing_story_is_a_404_on_every_route(client: httpx2.AsyncClient) -> None:
    assert (await client.get(url(MISSING))).status_code == 404
    assert (await client.post(url(MISSING, "/adopt"), json={"keys": []})).status_code == 404
    assert (await client.put(url(MISSING, "/pins"), json={"names": []})).status_code == 404
    assert (
        await client.put(url(MISSING, "/values"), json={"field": "place", "value": "x"})
    ).status_code == 404


# --- the story's own fields -------------------------------------------------------------------


async def test_a_story_can_write_a_field_of_its_own(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)

    response = await client.post(
        url(story.id, "/fields"),
        json={
            "label": "Who she is with",
            "icon": "👥",
            "hint": "the people next to her",
            "scope": "character",
        },
    )

    assert response.status_code == 201, response.text
    [field] = response.json()["fields"]
    assert (field["key"], field["label"], field["kind"], field["scope"]) == (
        "who-she-is-with",
        "Who she is with",
        "text",
        "character",
    )
    assert field["enabled"]
    assert field["words"] is None


async def test_a_words_field_needs_its_words_and_a_text_field_cannot_have_them(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)

    none = await client.post(url(story.id, "/fields"), json={"label": "Heat", "kind": "words"})
    text = await client.post(
        url(story.id, "/fields"), json={"label": "Heat", "kind": "text", "words": ["Low"]}
    )
    ok = await client.post(
        url(story.id, "/fields"),
        json={"label": "Heat", "kind": "words", "words": ["Low", "high", "Low", "Boiling"]},
    )

    assert (none.status_code, text.status_code, ok.status_code) == (422, 422, 201)
    assert ok.json()["fields"][0]["words"] == ["Low", "high", "Boiling"]


async def test_two_fields_with_the_same_label_get_different_keys(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)
    await client.post(url(story.id, "/fields"), json={"label": "Pose"})

    response = await client.post(url(story.id, "/fields"), json={"label": "Pose"})

    assert [f["key"] for f in response.json()["fields"]] == ["pose", "pose-2"]


async def test_the_name_line_is_built_in_so_no_field_can_take_its_label(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)

    named = await client.post(url(story.id, "/fields"), json={"label": "Name"})
    symbols = await client.post(url(story.id, "/fields"), json={"label": "???"})

    assert (named.status_code, symbols.status_code) == (422, 422)


async def test_a_story_keeps_at_most_so_many_fields(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)
    for n in range(24):
        assert (
            await client.post(url(story.id, "/fields"), json={"label": f"Field {n}"})
        ).status_code == 201

    response = await client.post(url(story.id, "/fields"), json={"label": "One more"})

    assert response.status_code == 422


async def test_a_field_can_be_renamed_switched_off_and_cleared_of_its_icon(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)
    await adopted(client, story.id, "outfit")

    response = await client.patch(
        url(story.id, "/fields/outfit"),
        json={"label": "What she wears", "enabled": False, "icon": None},
    )

    assert response.status_code == 200, response.text
    [field] = response.json()["fields"]
    assert (field["label"], field["enabled"], field["icon"]) == ("What she wears", False, None)
    assert field["hint"] == "what they are wearing now, briefly"  # left out: untouched
    assert field["key"] == "outfit"  # the key never changes


async def test_the_words_of_a_words_field_can_change_but_a_text_field_has_none(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)
    await client.post(
        url(story.id, "/fields"), json={"label": "Heat", "kind": "words", "words": ["Low"]}
    )
    await adopted(client, story.id, "place")

    words = await client.patch(url(story.id, "/fields/heat"), json={"words": ["Low", "High"]})
    text = await client.patch(url(story.id, "/fields/place"), json={"words": ["x"]})
    empty = await client.patch(url(story.id, "/fields/heat"), json={"words": []})

    assert words.json()["fields"][0]["words"] == ["Low", "High"]
    assert (text.status_code, empty.status_code) == (422, 422)


async def test_a_field_is_found_by_key_or_by_label(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)
    await adopted(client, story.id, "time")

    by_key = await client.patch(url(story.id, "/fields/time"), json={"enabled": False})
    by_label = await client.patch(url(story.id, "/fields/Day and time"), json={"enabled": True})
    nothing = await client.patch(url(story.id, "/fields/weather"), json={"enabled": True})

    assert (by_key.status_code, by_label.status_code, nothing.status_code) == (200, 200, 404)


async def test_deleting_a_field_takes_what_it_holds_and_switching_it_off_does_not(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)
    await adopted(client, story.id, "place", "time")
    await client.put(url(story.id, "/values"), json={"field": "place", "value": "the bar"})
    await client.put(url(story.id, "/values"), json={"field": "time", "value": "Day 2"})

    off = await client.patch(url(story.id, "/fields/place"), json={"enabled": False})
    gone = await client.delete(url(story.id, "/fields/time"))

    # Switched off, the field keeps what it holds.
    assert {(v["field"], v["value"]) for v in off.json()["values"]} == {
        ("place", "the bar"),
        ("time", "Day 2"),
    }
    assert [(v["field"], v["value"]) for v in gone.json()["values"]] == [("place", "the bar")]
    assert [f["key"] for f in gone.json()["fields"]] == ["place"]
    # The starter it came from is offered again.
    assert "time" in [s["key"] for s in gone.json()["starters"]]


# --- pins -------------------------------------------------------------------------------------


async def test_pinned_characters_replace_the_list_and_are_listed_once(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)

    first = await client.put(url(story.id, "/pins"), json={"names": ["Peach", "peach ", "Sammy"]})
    second = await client.put(url(story.id, "/pins"), json={"names": ["Lacie"]})

    assert first.json()["pins"] == ["Peach", "Sammy"]
    assert second.json()["pins"] == ["Lacie"]
    assert (await client.put(url(story.id, "/pins"), json={"names": [""]})).status_code == 422


# --- values by hand ---------------------------------------------------------------------------


async def test_a_value_set_by_hand_is_kept_marked_and_sent_with_the_next_prompt(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    story_id = story.id

    response = await client.put(
        url(story_id, "/values"),
        json={"field": "Outfit", "who": "Peach", "value": " a trench coat "},
    )

    assert response.status_code == 200, response.text
    [row] = response.json()["values"]
    assert (row["field"], row["who"], row["value"], row["by_hand"]) == (
        "outfit",
        "Peach",
        "a trench coat",
        True,
    )
    model.says("*Hi.*")
    await send(client, story_id, "One.")
    assert "- Outfit: a trench coat" in model.last["messages"][-1]["content"]


async def test_the_wrong_kind_of_value_is_refused(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)
    await client.post(
        url(story.id, "/fields"),
        json={"label": "Heat", "kind": "words", "scope": "character", "words": ["Low", "High"]},
    )
    await adopted(client, story.id, "place")

    scene_with_who = await client.put(
        url(story.id, "/values"), json={"field": "place", "who": "Peach", "value": "x"}
    )
    character_without = await client.put(
        url(story.id, "/values"), json={"field": "heat", "value": "Low"}
    )
    other_words = await client.put(
        url(story.id, "/values"), json={"field": "heat", "who": "Peach", "value": "Boiling"}
    )
    missing = await client.put(url(story.id, "/values"), json={"field": "pose", "value": "x"})

    assert [r.status_code for r in (scene_with_who, character_without, other_words, missing)] == [
        422,
        422,
        422,
        404,
    ]
    assert "Low, High" in other_words.json()["detail"]


async def test_a_blank_value_clears_it(client: httpx2.AsyncClient, session: AsyncSession) -> None:
    story = await a_played_story(session)
    await adopted(client, story.id, "place")
    await client.put(url(story.id, "/values"), json={"field": "place", "value": "the bar"})

    response = await client.put(url(story.id, "/values"), json={"field": "place", "value": "  "})

    assert response.json()["values"] == []


async def test_a_reply_written_after_a_hand_set_value_replaces_it(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    story_id = story.id
    await client.put(url(story_id, "/values"), json={"field": "place", "value": "her flat"})
    model.says("📍 Place: the bar\n*Hi.*")

    await send(client, story_id, "One.")

    [row] = (await client.get(url(story_id))).json()["values"]
    assert (row["value"], row["by_hand"]) == ("the bar", False)


# --- /status ----------------------------------------------------------------------------------


def test_the_command_is_split_at_the_equals_sign_and_the_last_colon() -> None:
    assert split_command("Peach: Outfit = nothing") == ("Peach", "Outfit", "nothing")
    assert split_command("Place = the bar: closed") == ("", "Place", "the bar: closed")
    assert split_command("Day and time=") == ("", "Day and time", "")
    assert split_command("Outfit nothing") is None


async def test_the_command_sets_a_value_without_a_model_call_or_a_message(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    story_id = story.id

    streamed = await stream(
        client, f"/stories/{story_id}/send", text="/status Peach: Outfit = nothing but heels"
    )

    assert streamed.done["text"] == "Outfit for Peach is now nothing but heels."
    assert model.calls == []
    values = (await client.get(url(story_id))).json()["values"]
    assert [(v["who"], v["value"], v["by_hand"]) for v in values] == [
        ("Peach", "nothing but heels", True)
    ]
    assert (await client.get(f"/stories/{story_id}")).json()["messages"][-1]["role"] == "assistant"


async def test_the_command_clears_a_value_and_says_so(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_story_with_fields(session)
    await client.put(url(story.id, "/values"), json={"field": "place", "value": "the bar"})

    streamed = await stream(client, f"/stories/{story.id}/send", text="/status Place =")

    assert streamed.done["text"] == "Place cleared."
    assert (await client.get(url(story.id))).json()["values"] == []


async def test_the_command_refuses_before_it_streams(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_story_with_fields(session)

    no_equals = await stream(client, f"/stories/{story.id}/send", text="/status Place the bar")
    no_field = await stream(client, f"/stories/{story.id}/send", text="/status Weather = rain")
    scene_who = await stream(client, f"/stories/{story.id}/send", text="/status Peach: Place = x")
    no_argument = await stream(client, f"/stories/{story.id}/send", text="/status")

    assert [s.status for s in (no_equals, no_field, scene_who, no_argument)] == [
        422,
        404,
        422,
        422,
    ]
    assert (await client.get(url(story.id))).json()["values"] == []


async def test_the_commands_list_includes_status(client: httpx2.AsyncClient) -> None:
    listed = (await client.get("/commands")).json()

    [spec] = [c for c in listed if c["name"] == "status"]
    assert spec["cost"] == "write"
    assert spec["usage"] == "/status [<who>: ]<field> = <value>"


async def test_fields_survive_in_the_order_they_were_written(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)
    await adopted(client, story.id, "mood")
    await client.post(url(story.id, "/fields"), json={"label": "Pose"})
    await adopted(client, story.id, "time")

    fields = await blocks.fields_of(session, story.id)

    assert [(f.key, f.position) for f in fields] == [("mood", 0), ("pose", 1), ("time", 2)]
