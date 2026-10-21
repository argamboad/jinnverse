# Two clients, one API

JinnVerse has one API and two clients, and until Step 11 every feature arrived in both: a web
issue and a terminal twin in the same milestone. Then came a web redesign, four steps long,
built from a design handoff for the web alone. Each of those steps was right on its own terms,
and at the end of them the terminal client had quietly fallen behind on the library, the part of
the app where the owner curates characters, personas and pieces by hand.

Step 17 caught it up. It was nine issues in one pull request: eight features and this chapter.
The interesting part is less the features than how a gap like this opens, how it was found, and
what closing it taught.

## How the drift happens

Nobody decided the terminal client should lack a history view. The web's library editor had one
from Step 8, because the API had `GET /library/{shelf}/{id}/history` from Step 4 and the web
editor was built with the endpoint in view. The terminal client's library came in Step 9, built
from custom-airp's terminal views, and airp kept one `.bak` of the last save, so its donor had
nothing to port. Two clients built from two different references end up with two different
feature sets, even over one API.

The redesign widened it. Its issues were labelled `area/client`, the web, and nothing in the
workflow asks "and the terminal?" when an issue only names one client.

::: dotnet
This is the familiar problem of a Blazor front end and a WPF tool over the same ASP.NET Core
API. The API is shared, so it feels like the two are in step; but a feature is only *in* a
client once that client calls the endpoint and shows the result. Shared DTOs don't share
screens.
:::

## Finding it: an inventory, file by file

The gap was found by asking a plain question, "did the terminal get the library changes too?",
and answering it with evidence rather than memory. A read-only agent read the web's five library
routes and the terminal's three library modules and returned one table: each capability, where
the web does it (file and line), where the terminal does it, and the endpoint behind it. The
useful rows were the ones that said *no* with proof: "no `history` method in `api.py`; the only
mention in `library.py` is the delete dialog's *Its history stays*".

Two things came out of it that were not on anyone's list:

- **An entry hidden in the terminal could not be found there again.** A name starting with `_`
  is kept but not listed, and the terminal never asked for hidden entries, so `F2` to `_draft`
  made an entry unreachable from the client that renamed it.
- **The API already sent what the terminal lacked.** The list response had carried `used`, the
  number of stories using each entry, since Step 14. The terminal's model simply did not declare
  the field.

## Fields the client was throwing away

That second point is a Pydantic default worth knowing. A `BaseModel` ignores keys it does not
declare:

```python
class Entry(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    preview: str
    description: str | None = None
    used: int = 0  # new in Step 17; the JSON had it since Step 14
```

Before the last line, `Entry.model_validate(json)` took the response with `used` in it and kept
everything else. No error and no warning: the number arrived on every list call and was dropped.

::: dotnet
`System.Text.Json` does the same by default: unknown properties are skipped unless you set
`JsonUnmappedMemberHandling.Disallow`. Pydantic's equivalent is `model_config =
ConfigDict(extra="forbid")`. Neither is the right default for a client, which should keep working
when the server adds a field. But it means "the API returns it" and "the client has it" are two
different claims, and only reading the model tells you which one is true.
:::

## A restore is just a save

The web's history drawer has *Put in the editor*: it loads an old version's name, text, opening
and description into the form, and saving makes them the newest version. There is no restore
endpoint and none is needed. The terminal does the same through the save it already had:

```python
saved = await self._save(
    entry.id, entry.version,           # the version the history was opened on
    name=old.name, text=old.text,
    opening=old.opening if character else None, clear_opening=character,
    description=old.description, clear_description=True,
)
```

Two properties come for free. The history only grows: version 3 put back becomes version 7, and
putting back version 6 undoes it. And a change made elsewhere meanwhile meets the same conflict
screen as any save, because the save carries the version the history screen was opened on.

::: dotnet
This is optimistic concurrency doing a second job. With EF Core you would mark `Version` as a
concurrency token and let `SaveChanges` throw `DbUpdateConcurrencyException`; here the API
compares versions and answers 409 with the entry as it is now. A restore that goes through the
same path inherits the protection without a line of its own.
:::

## A few questions, one at a time

The web's form asks for a new entry's name, description and opening on one screen. A terminal
asks one question per line. `N` now gathers its answers in a small record before anything is
saved:

```python
@dataclass(slots=True)
class Pending:
    name: str
    slot: str | None = None   # a piece's slot; None for a character, persona or snippet
    label: str = ""
    voice: Voice = "he"
    short: str | None = None
```

Each answer moves the screen to its next mode (`naming`, then `short-new` for a name piece, then
`describing-new`), and only the last one saves. `Esc` at any question clears `_pending` and
creates nothing.

::: dotnet
A `@dataclass` is a C# `record class`, or a plain class with an auto-generated constructor,
equality and `ToString`. `slots=True` is about memory, not behaviour: instances get no
per-object `__dict__`. The modes are the states of a small state machine, of the kind a WPF
wizard keeps in a `CurrentStep` enum.
:::

## Two Textual details that bite

Both came up in this step, and both are the kind of thing that looks like a bug in your code:

- **An `Input` selects all its text when it gets the focus** (`select_on_focus=True`). For a
  suggested persona name that is what you want: typing replaces it. For the builder's offered
  slot, `vehicle `, it is not, because the name typed after it replaced it. The builder now sets
  `select_on_focus` per question.
- **A list item can be two rows.** `Rows` draws `rows_per_item` lines per item, so the library's
  entries became the name plus a muted line (`v3 · in 2 stories · The innkeeper`), as on the web.
  The pieces shelf kept one row, because its names already say slot and voice.

## A test that keeps help honest

The help screen had no section for the persona builder; its keys lived only in the builder's
own legend. Adding the rows fixes it today. A test keeps it fixed:

```python
@pytest.mark.parametrize(
    ("hints", "section"),
    [
        (LibraryScreen.HINTS, "Library"),
        (HistoryScreen.HINTS, "An entry's history"),
        (PersonaBuilderScreen.HINTS, "Persona builder"),
        (NewStoryScreen.HINTS, "New story"),
    ],
)
def test_every_key_in_the_legend_is_in_help(hints, section) -> None:
    missing = {k for hint in hints for k in keys(hint.key)} - in_help(section)
    assert not missing
```

Writing it turned up two more: `Ctrl+B` and `Space`, which the New story legend had shown since
Steps 10 and 11 with no row in help. Help is data (`SECTIONS`), and so are the legends
(`HINTS`), so the test needs no screen and no terminal.

::: dotnet
`@pytest.mark.parametrize` is xUnit's `[Theory]` with `[InlineData]` rows: one test function,
one result per row. It works because both sides are data. The .NET habit of keeping menus and
shortcut tables in resources, rather than spread through XAML, pays off the same way.
:::

## What this step teaches

- **A shared API does not mean shared features.** Ask of every client-side issue: which clients
  does it name, and which should it?
- **Answer "do we have X?" with evidence.** An inventory with file and line beats anyone's memory
  of four steps of work, and it finds the gaps nobody listed.
- **Read your models against the wire.** A client that ignores unknown fields stays robust and
  quietly loses information. Both are true at once.
- **Make drift a failing test** wherever both sides are data.
