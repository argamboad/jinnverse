# The lorebook

Step 24 began with a document, not a bug. The owner brought an architecture review written for
a different roleplay stack and asked what in it was worth taking. Most of it was not: it proposed
a fixed window of the last thirty messages where chapter 5 counts tokens and chapter 6 keeps what
leaves the window; a second model swapped in by a regular expression on the reader's message,
which airp built and took out (#140) because the model billed as most explicit wrote about like
the default; and a "jailbreak" system prompt for a model that does not refuse. One idea survived
the reading: a **lorebook**, authored text that belongs to a character and is sent only when the
scene calls for it. This chapter is why that one survived, what the card that made the case
looks like, and how the feature was shaped by the lessons the earlier chapters paid for.

Seven issues, one pull request: the storage (#266), the matcher and the layer (#267), the two
clients (#268, #269), a documentation note on models (#270), this chapter (#271), and the
owner's list for after the merge (#272).

## One card in fifty-three

Fifty-three characters on staging. Fifty-two of them are between 7,000 and 19,000 characters,
roughly 1,700 to 4,500 tokens, and fit the 32,000-token budget whole with room for a long story.
One is 115,475 characters. *Blake Jameson University* is a world, not a character: a campus, seven
Greek houses, two timetables, a dining guide, the rule that "the user decides who they are and
the world reshapes to fit", and a cast of forty-three people with a full sheet each. The cast
alone is 86,718 characters.

The numbers below are estimates, because tiktoken counts tokens and a database query counts
characters; the ratio is the one tiktoken measured on the Gilded Heron card, which is prose of
the same style.

| Piece | Tokens |
|---|---|
| The whole card | 27,400 |
| The cast section alone | 20,500 |
| The world section | 4,500 |
| Who plays whom, how you write, how you behave | 1,900 |
| Context budget | 32,000 |
| Left for persona, dials, facts, summaries and history | about 4,000 |

Four thousand tokens is six to ten turns. After that, chapter 6's memory compresses continually,
and each summary it adds takes from the same four thousand. The story would live almost entirely
in summaries. The brief's lesson on budgets — attention thins out, every token is paid for every
turn — runs the other way here: it is the card that thins the story.

The cheap alternative is honest and insufficient. Raising the budget to 48,000 makes the card
playable today, paying for 27,000 unchanging tokens every turn, discounted only on hosts that
cache, and buys a few more turns before the same wall. The real fix is to stop sending forty-three
sheets to a scene with four people in it.

## What an entry is, and what it is not

An entry is a piece of the card moved out of it — a cast member's sheet, a building, a timetable
— with the **keys** that bring it in: a name, a nickname, a role, a place. It comes into the
prompt only while one of its keys is in the scene. The name of an entry is the editor's handle,
as a snippet's is, and is never sent; the text is sent whole.

Three things an entry is not, each a boundary with something built earlier:

- **Not a fact.** Chapter 6's facts hold what *happened*: she is angry since Tuesday, the debt is
  paid. An entry holds what the author *wrote*: who Jacqueline Kai is. The BJU card's rule that
  every character carries a private, unstated feeling about the user that moves only through
  what actually happens is the facts layer's job, word for word. The two do not overlap if the
  boundary is authored versus happened.
- **Not a snippet.** A snippet (chapter 4) is triggered by the author typing `:name` and copied
  into the message, never read again. An entry is triggered by the scene and never enters the
  transcript.
- **Not a type of character.** A character has a card, and now zero or more entries. A card with
  none is sent exactly as before: no flag, no second kind of character, nothing in the schema
  that says which is which. The builder's existing tests, which assert the full message list for
  a prompt built from the Gilded Heron, are the proof: they did not change.

## The table: a Postgres array, and the history widened

```python
class LoreEntry(LibraryEntry, Base):
    __tablename__ = "lore_entries"
    __table_args__ = (
        Index("uq_lore_entries_character_name_lower", "character_id", text("lower(name)"),
              unique=True),
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    keys: Mapped[list[str]] = mapped_column(ARRAY(String(60)))
    text: Mapped[str] = mapped_column(Text)
```

The `LibraryEntry` mixin from chapter 4 brings the id, the name, the version and `updated_at`,
so an entry saves the way a card saves: `PATCH` with the version the editor started from, a
`409` carrying the current text when it moved on, and a history row per version. The history
table's `CHECK (kind IN (…))` had to widen to admit `lore`, and the migration's downgrade meets a
rule chapter 4 set: the history's trigger refuses a delete. So the downgrade does not delete the
`lore` rows; it drops the wider check and adds the narrower one back `NOT VALID`, which Postgres
allows — it holds for every row written from then on and tolerates the ones already there — and
Alembic has no word for, so it is one line of raw SQL.

`keys` is a Postgres array, `TEXT[]` in the migration. The review document indexed its array with
GIN and queried it with the overlap operator `&&`, which is the right tool for a million entries
and the wrong one for forty: a character's entries are read in one query and matched in Python,
where the matching rule can be whole words and case-insensitive without an expression index.

::: dotnet
EF Core on Npgsql maps `string[]` to `text[]` the same way, and would let you write
`entries.Where(e => e.Keys.Any(k => tokens.Contains(k)))`, translated to `&&`. The choice here is
not a limitation of the ORM; it is that the data is small and the rule is textual. A list of forty
strings is a `foreach`, not a query plan.
:::

The entries belong to the character, `ON DELETE CASCADE`. A character cannot be deleted while a
live story uses it (chapter 4's `RESTRICT` from stories), so nothing in play loses its entries;
once no story needs the character, its entries go with it. They are listed in creation order:
the ids are UUIDv7 (chapter 2), so `ORDER BY id` is the order the owner split the card in, which
is the order of the card.

## The matcher: six turns and the status block

```python
def matched(entries, recent, status_lines=()) -> list[Lore]:
    scene = list(recent[-LOOKBACK:])
    status_text = "\n".join(status_lines)
    found = []
    for position, entry in enumerate(entries):
        pattern = _pattern(entry.keys)
        if status_text and pattern.search(status_text):
            found.append(Lore(position, entry.text, len(scene)))
            continue
        newest = next((i for i in range(len(scene) - 1, -1, -1)
                       if pattern.search(scene[i])), None)
        if newest is not None:
            found.append(Lore(position, entry.text, newest))
    found.sort(key=lambda hit: (-hit.freshness, hit.position))
    return found
```

Pure, like the builder: strings in, dataclasses out, tested in milliseconds. Four decisions are in
those lines, and each answers a way the document's design would have failed.

**Where to look.** The document scanned the incoming user message. That misses the character's
own mentions — the model brings Sabrina into the room, and the next prompt has no sheet for her —
and it drops a character from the prompt the moment nobody says her name. The matcher looks in
the last six visible turns, `LOOKBACK = 6`: the same six that chapter 6's summariser never
compresses, the scene in progress. Six is the hysteresis. A character stays through a short
exchange about something else and goes once the scene has moved on, and the test says exactly
that: a name in the seventh turn back fires nothing.

**The status block.** Chapter 11 gave every story a block the model writes at the top of each
reply — the time, the place, and a line per character in the scene — which the app reads back
and stores. That is a better trigger than prose. "Stallion Arena" in the place field keeps the
arena's entry in for as long as the scene stays there, whether or not anyone says its name, and
"Monday, 6:00 AM" would key a practice timetable the same way. The status counts as the newest
mention, fresher than any turn.

**A key is a whole word.** `(?<!\w)(?:jax|bartender)(?!\w)`, case-insensitive: `jax` is not in
`Jaxon` but is in `Jax's`, and a key may hold a space, so `preston centre` is one key. Accents
are not folded, because the text spells them and a key can too. The API lowercases and trims the
keys on the way in; the clients read them from one comma-separated line.

**No cascading.** An entry's own text is never looked in. Isaure's sheet names Derrow & Sons, and
the minor figures' entry is keyed on `derrow`; her entry alone does not pull theirs. SillyTavern
calls the opposite "recursive scanning" and offers it as an option; with forty-three sheets
that name one another, it would bring the whole cast back in three hops.

The `freshness` on each hit is for the builder, next.

## The layer: after the history, under a cap

Chapter 5 settled the order of the layers and the reason for it: a provider's prefix cache keeps
everything up to the first byte that changed, so the volatile layers go last. The review document
put its lore slot second, before the history, as the SillyTavern default does. Every change of
scene would then have re-sent the whole transcript at full price. Here the lore goes after the
history, beside the recalled memories, for the same reason the memories are there:

```python
ORDER = ("character", "persona", "directives", "world", "summaries",
         "history", "memories", "lore", "trackers", "status", "reminders", "instruction")
```

And it is capped. Four long recalled turns once filled a 60,000-token prompt, which is why the
memories take at most `recall_percent` of the budget; a scene at a crowded bar could call for
eight sheets of five hundred tokens, so the lore takes at most `lore_percent`, twenty by default.
`_fit_lore` is `_fit_memories` with a different sort: the hits arrive freshest first and are
kept while they fit, then put back in the order of the card, so the model reads them as the
author wrote them. The audit line counts the layer and what it dropped, as it does every other.

The matching happens inside `memory.compose`, once per prompt, on the end of the transcript and
the status block, which no summary made along the way changes. A turn, an out-of-character
question, a review of the facts and a rebuild all go through `compose`, so all four see the same
entries — chapter 17's rule that the reviewer sees what the reply model sees holds without a
second thought. A character without entries costs one query and sends what it always sent.

::: note
The reserve chapter 6 computes before deciding what to compress includes the lore, because the
reserve builds every fixed layer with the history left out, and the lore is fixed for a turn. The
summariser and the builder still agree on how much room the history has.
:::

## Testing on the real thing

The brief's rule for the memory applies: every test uses a character of realistic size, never a
few inline words. The dummy fixture gained `lore.json`, the Gilded Heron's six cast sheets as
entries with keys — Isaure, Blake, Mags, Anselm, the captain, the minor figures — and the tests
are about them. A turn that says "I nod to the inspector in the corner" gets Blake's sheet and
Isaure's, who is named in the opening still in scene, and not the captain's, who is at berth
six; the layer sits after the transcript; the audit counts it. A place standing in the
status block keeps its entry in through six turns that never name it.

The cap test is the one worth reading. It calls every sheet into one turn, sets the budget so
that twenty percent holds about two of them, and asserts which two: Isaure, the freshest, and
Blake, the first named in the older turn, sent in card order with Isaure first, and `dropped 3`
in the audit. A test that asserted "some were dropped" would pass with the wrong two.

::: try
Add a seventh fixture entry keyed on a word that appears in Isaure's sheet but not in the Heron's
opening, and run the matcher tests. None should change: the sheet's text is never looked in.
Then make the matcher scan the entries' own text and watch which test catches it.
:::

## What the document got wrong, and why it matters

A review written for one stack and read against another is a useful exercise exactly because its
mistakes are specific. The fixed window of thirty messages ignores that turns differ in length by
a factor of ten and that what leaves the window must be kept somewhere, which is what chapters 5
and 6 are. The regex model router — `kill|attack|torture|nsfw|…`, swap to a Llama finetune —
fires on "execute the plan", changes the character's voice mid-scene, throws away the cached
prefix, and reruns an experiment airp already ran: six models per story, no difference a reader
could name, taken out. The "act as unhinged" system prompt exists to push a model past a refusal
that the default model does not make, and what it does produce is shouting.

What the document was right about is the shape of the problem. Its examples of failure —
instruction drift, every NPC sounding the same, the model writing the reader's actions — are real,
and this app answers them in places the document did not know existed: the reminders layer
repeating the dials after the history (chapter 7's #167), the pov and npc-liveliness dials, the
card's own `WHO PLAYS WHOM` section. The lorebook is the one answer the app did not have.

Two of the document's four model slugs did not exist on OpenRouter under the names it gave. The
live ones are written beside `JINNVERSE_MODEL` in `.env.example` now (#270), with context, price
and the caveat each carries, so trying one is a line in `.env` for every story at once, judged on
real stories, as the brief says a model is judged.

## The two clients

Both clients edit entries under a character, and neither reaches the database. The web app
(#268) puts a **Lore** section under the card and the opening: the entries in order, each with
its keys as a note and the first line of its text, opening into a small editor of its own — name,
keys on one line, text — that saves from its own buttons, with the version check and the
conflict notice the card has. Chapter 14's rule that documents save when you say so holds; an
entry half-edited blocks leaving the page like a half-edited card does.

The terminal client (#269) gives the lore a screen of its own, `L` from the characters shelf:
the entries down the left with their keys under each name, the text on the right, and the
library's one-question-at-a-time input for `N` (the name, then the keys, then the editor on a
skeleton), `K` and `F2`. The conflict screen, which the library had owned, moved to `conflict.py`
and became generic over what it shows, because the API client now parses a lore entry's `409`
as readily as a card's:

```python
class ConflictScreen[T: Conflicted](View):
    def __init__(self, message: str, theirs: T, save: Callable[[T], Awaitable[object]]) -> None:
```

`Conflicted` is a `Protocol` with three read-only properties — `name`, `version`, `text` — which
both Pydantic models satisfy without saying so.

::: dotnet
A `Protocol` is an interface the implementer never names: structural typing, which C# has only
at the edges (`foreach` needs a `GetEnumerator`, not `IEnumerable`). `class ConflictScreen[T:
Conflicted]` is Python 3.12's syntax for `class ConflictScreen<T> where T : IConflicted`. Pyright
checks both at the call site, and the tests had to narrow with `isinstance` where a C# test would
have cast.
:::

## What the step leaves for the owner

The feature is built against a card that no story on staging has played yet, so the measurement
is still to come. The owner's issue (#272) is the plan: migrate Neon, deploy, reinstall the
terminal client, and then copy *Blake Jameson University* to a second card with the cast section
replaced by a one-line roster and the forty-three sheets, the Greek houses, the dorms, the dining
and recreation places and the timetables as entries. The original stays as it is. Two stories,
the same opening, the same first turns, and the audit says per reply what the character layer
and the lore cost and how much history each one kept. That is the number the brief asks for
before a lesson is believed, and it is the first thing chapter 21 should report.

One design question is deliberately left open: how a card becomes entries. This step offers the
editors, which is forty-three copy-pastes for the card in question. An extraction that proposes
the split and lets the owner confirm it, the way `/review` proposes and confirms, is the obvious
next tool — and it should be built only if the comparison says the lorebook earned it.
