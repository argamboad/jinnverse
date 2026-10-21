"""Status fields: the starter set, a story's own fields, and adopting the starter ones (#170)."""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from jinnverse import blocks
from jinnverse.models import StatusKind, StatusScope
from tests.test_turns import a_played_story


def test_the_shipped_starter_set_reads_whole() -> None:
    found = blocks.starters()

    assert [s.key for s in found] == ["time", "place", "outfit", "mood"]
    assert [(s.scope, s.kind) for s in found] == [
        (StatusScope.SCENE, StatusKind.TEXT),
        (StatusScope.SCENE, StatusKind.TEXT),
        (StatusScope.CHARACTER, StatusKind.TEXT),
        (StatusScope.CHARACTER, StatusKind.TEXT),
    ]
    assert [s.icon for s in found] == ["📅", "📍", "👗", "🎭"]
    assert all(s.hint for s in found)


def test_a_starter_that_cannot_be_used_is_left_out_and_the_rest_are_kept() -> None:
    text = json.dumps(
        {
            "fields": [
                {"key": "place", "label": "Place", "scope": "scene", "kind": "text"},
                {"key": "Not A Slug", "label": "Bad key", "scope": "scene", "kind": "text"},
                {"key": "pose", "label": "Pose", "scope": "nowhere", "kind": "text"},
                {"key": "age", "label": "", "scope": "character", "kind": "text"},
                "not an object",
            ]
        }
    )

    assert [s.key for s in blocks.parse_starters(text)] == ["place"]
    assert blocks.parse_starters("{}") == ()
    assert blocks.parse_starters('{"fields": 3}') == ()


def test_a_label_becomes_a_key() -> None:
    assert blocks.slug("Day and time") == "day-and-time"
    assert blocks.slug("  Who's with her?  ") == "who-s-with-her"
    assert blocks.slug("Ñandú") == "and"  # ASCII keys only: the label keeps the accents


async def test_a_story_has_no_fields_until_it_adopts_some(session: AsyncSession) -> None:
    story = await a_played_story(session)

    assert await blocks.fields_of(session, story.id) == []


async def test_adopting_starters_gives_the_story_its_own_rows_in_order(
    session: AsyncSession,
) -> None:
    story = await a_played_story(session)

    adopted = await blocks.adopt(session, story.id, ["mood", "place", "unknown"])

    assert [(f.key, f.position, f.enabled) for f in adopted] == [
        ("place", 0, True),
        ("mood", 1, True),
    ]
    place = adopted[0]
    assert (place.label, place.icon, place.scope, place.kind) == ("Place", "📍", "scene", "text")
    assert place.hint == "where the scene is, briefly"
    assert place.words is None


async def test_adopting_again_switches_a_field_on_and_keeps_what_the_story_changed(
    session: AsyncSession,
) -> None:
    story = await a_played_story(session)
    [outfit] = await blocks.adopt(session, story.id, ["outfit"])
    outfit.label = "What she wears"
    outfit.enabled = False
    await session.flush()

    adopted = await blocks.adopt(session, story.id, ["outfit", "time"])

    assert [(f.key, f.label, f.enabled) for f in adopted] == [
        ("outfit", "What she wears", True),
        ("time", "Day and time", True),
    ]
