# Status blocks

The owner showed an example from another app: a character whose every reply opens with a small
block — the day and time, the place, her name, her outfit, her mood — and then the prose. It is the
kind of fact a story needs to stay consistent and a model is bad at keeping: what she was wearing
three hundred turns ago is in no summary. This chapter is the feature that keeps it. It was
eight issues in one pull request, and it is mostly about one idea: **state the app keeps, derived
from the transcript, and given back to the model at the end of the prompt.**

It is also the second time this project has met the same failure. Chapter 7 has a section on a
rule that has to be said twice (#167): a directive written once, early, is outweighed by a long
history that does not follow it. A status block asked for in a character card fails the same way,
and for the same reason, so everything here is built around not trusting the model to remember the
format or the values.

## What the model writes, and what the app keeps

The block stays **in the reply**, as text at the top, exactly as the example has it. It is not
stripped out and shown elsewhere, because the history the model reads next turn should contain it:
the model copies what it sees. What the app adds is a second copy that cannot drift: a table of
what each line holds, read back from each reply.

There are two kinds of line. **Scene** lines have one value for the whole scene (the day, the
place); **character** lines have one value per named character (the outfit, the mood). Each
character who speaks or acts gets a block of their own, opened by a **name line**:

```
📅 Day and time: Day 1, 11:52 PM
📍 Place: the VIP booth
📛 Name: Peach
👗 Outfit: black micro bikini, open robe
🎭 Mood: guarded, teasing
*Peach barks a short laugh.*
```

The name line is built in. A character's block is found by it, so it is never a field a story can
switch off or rename, and `Name` is reserved as a label.

## The data

Three tables, and the starter set as data:

```python
class StatusField(Base):      # a line a story asks for
    key, label, icon, hint
    kind: "text" | "words"    # words: only these allowed words are kept
    scope: "scene" | "character"
    words: list[str] | None   # JSONB
    enabled, position

class StatusValue(Base):      # what a line holds, for the scene or one character
    field_key, subject, subject_key, value
    updated_at_sequence       # the message that last wrote it
    by_hand                   # set by the owner, not read from a reply

class StatusPin(Base):        # a character whose state is always sent
```

A story has only the fields it **adopted**. A story with none enabled behaves exactly as it always
did: no layer, no parsing, no extra token. The shipped starter set (time, place, outfit, mood) is a
JSON file, like the dial pack of chapter 7, so adding a starter is not a code change; adopting one
copies it into the story's own rows, and from then on the story's copy is its own.

`subject_key` is the name lowercased and trimmed, which is what names are matched on: `Peach`,
`PEACH` and ` peach` are one character, while the spelling the model first used is kept for
display. The unique constraint is on `(story, field, subject_key)`.

::: dotnet
`StatusField` is a configuration row, the way an `IOptions<T>` section would be if each story had
its own settings file; `StatusValue` is the state it configures. The `JSONB` column is EF Core's
`HasColumnType("jsonb")` with a `List<string>` value converter; the `CHECK` constraints on `kind`
and `scope` are the database refusing what the code would never write, the same belt and braces as
chapter 10's `PieceSlot`.
:::

## Reading a reply

The parser is a pure function, `blocks.read(reply, fields, default_subject)`, tested without a
database. A line is `icon label: value`, with either part of the tag optional, so the three forms a
model drifts between are the same line:

```python
LINE = re.compile(
    r"^\s*(?:[>#•-]\s*)*"
    r"(?P<icon>[^\w\s:>#•-]{1,8})?\s*"
    r"(?P<label>\w[\w '" + RIGHT_QUOTE + r"/&-]{0,58}?)?\s*"
    r":\s*(?P<value>\S.*?)\s*$"
)
```

`📍 Place: the bar`, `📍: the bar` and `Place: the bar` all match. Markdown the model wraps a line
in (`**Place:**`) is stripped first, and an icon is compared without its invisible variation
selector. The rules are small and each one is a failure that would otherwise be real:

- A line that is **not a field of the story**, or that merely looks like a label (`She says: not
  tonight`), is prose, and **prose closes the block**. A character line after prose has no name
  before it.
- A character line with no name line before it belongs to the **story's character**
  (`default_subject`), so a single-character chat needs no name line; with none known it is
  dropped, never guessed.
- A **words** field keeps only its own words, in the order written, case-insensitively and
  without repeats; a value with none of them is not stored at all.
- `unchanged`, a dash or `n/a` mean "nothing new", and the stored value stays.
- A name line's value is cut at a bracket and must be a few words: a sentence that happens to start
  with `Name:` is not a name.

::: dotnet
`re.compile` with named groups is `Regex` with `(?<name>…)`; the pattern is compiled once, at
import, like a `static readonly Regex` with `RegexOptions.Compiled`. The ambiguous typographic
quote is built with `chr(0x2019)` rather than typed: the linter flags the look-alike character, and
a regular expression is the worst place for a character that looks like another.
:::

## The state is a function of the transcript

This is the decision the chapter turns on. The obvious design stores each reply's changes and
undoes them when a reply goes away. It needs a history table and an undo for every way a reply can
disappear: a **reroll** hides the newest reply, a **cut** hides many, a **branch** copies some.
Miss one and a value written by a reply that no longer exists stays behind — and in this app that
is not rare, since the reply a reader rerolls is often the one that changed the outfit.

So the app stores no history. `blocks.replay` reads the **visible** replies again, oldest first,
and rebuilds the state:

```python
async def replay(session, story) -> None:
    await session.execute(
        delete(StatusValue).where(StatusValue.story_id == story.id, StatusValue.by_hand.is_(False))
    )
    ...
    for sequence, text in replies:                 # visible assistant messages, in order
        _apply(session, story.id, stored, read(text, fields, name), sequence)
```

It runs when a reroll hides a reply (and again if the model then fails and the reply is shown
again), when a cut hides turns, and for a branch, whose copy now holds the state *as it stood at the
point* — which the meters of chapter 7 cannot do. Reading eight hundred replies is eight hundred
passes of a regular expression, and it only happens when the transcript changes.

What a person set by hand has no reply to be re-read from, so it is the one thing kept (`by_hand`).
It yields to a reply written *after* it and not to one written before, which is exactly what a
replay meets:

```python
if row.by_hand and (row.updated_at_sequence or 0) >= sequence:
    continue            # the owner's value is newer than this reply
```

A hand-set value takes the sequence of the newest message when it was set, so a tie goes to the
owner.

::: note
A field switched **off** is not asked for and not read from a live reply, but `replay` still reads
every field the story has: switching a line off keeps its values, and switching it on again shows
the last outfit, not an empty one.
:::

## What goes into the prompt

A new layer, `status`, sits after the history and the meters and before the reminders and the
turn's instruction. It carries two things: the **format** the model is to write, built from the
story's own fields, and the **state** as it stands.

```
Every reply begins with a status block that keeps this story's state. First the scene lines,
then, for each character who speaks or acts in the reply, their name line followed by their
lines ...

📅 Day and time: <the day and the time of day, as the story counts them>
📍 Place: <where the scene is, briefly>
📛 Name: <the character's name>
👗 Outfit: <what they are wearing now, briefly>

Change a line only when the story changed it; otherwise write it as it stands below. ...

Where things stand now:
Scene
- Day and time: Day 1, 11:52 PM
Peach
- Outfit: black micro bikini, open robe
```

That is about 230 tokens for the starter set, and it is at the end on purpose: the model weighs
the last thing it reads most, and a format stated only at the top of a 90,000-token prompt is the
format that gets dropped (chapter 7, #167). A word field lists its words, so the model sees what
it may write; a text field shows the owner's hint.

The state is the part that has to be bounded. The BJU story has more than forty characters, and
most are offstage at any moment, so sending every character's last outfit every turn would cost a
great deal and say nothing. The rule is `render`:

- the **scene** is always sent;
- a **character** is sent when they wrote a line within the last 12 messages, or are **pinned**,
  and at most 12 characters are sent, pinned first and then the most recent;
- a character who comes back after a long absence is simply sent again with their last known
  state — which is the whole point of keeping it.

The layer is passed by turns and by the rebuild (so the summaries land where playing would have put
them) and **not** by `/ask`: a question out of character is an answer, not a reply, and a format
for replies would only confuse it. It appears in the audit line as `status N`.

## The API and /status

Every call that changes something answers with the **whole state**, so a client draws one response
and keeps no copy of its own to drift. That one rule removed a class of bugs in both clients: no
screen merges a patch into what it holds, it replaces what it holds.

```
GET    /stories/{id}/status            fields, values, pins, and the starters not yet adopted
POST   /stories/{id}/status/adopt      give the story starter fields
POST   /stories/{id}/status/fields     a field of its own (the key comes from the label)
PATCH  /stories/{id}/status/fields/{key}   rename, icon, hint, words, on/off, position
DELETE /stories/{id}/status/fields/{key}   delete a field with what it holds
PUT    /stories/{id}/status/pins       the characters always sent
PUT    /stories/{id}/status/values     set a value by hand; blank clears it
GET    /status-starters                the starters, before a story exists
```

A field's key, kind and scope **never change**: the values already read were read under them.
Deleting a field takes its values; switching it off does not. `/status [who: ]field = value` does
the same as the last route from the composer, with no model call and no message, and refuses
*before the stream opens* so a mistake is a 4xx and not a stream of one — the same shape as
`/tracker`.

The new-chat screen needs the starters before the story exists, which is why `GET /status-starters`
is a route of its own. It came with the screen that needed it, not with the rest of the API.

## The clients

**Web.** A fourth tab, *Status*, beside Dials, Meters and This prompt: the fields with a switch
each, the starters, an *Add a field* form, the pinned characters as chips, and what each line holds
with an *Edit*. The switches are the quick on/off from the chat. Under the app bar of a story, a
**strip** shows the scene's lines and who is in scene (pinned first); a tap opens the tab. The
new-chat screen lists the starters unticked, and the ticked ones are adopted right after the story
is created — if that fails the story still starts, and a note says so, because losing a story to a
failed extra is worse than starting without it. The design was shown in the dark and light themes
and approved before it was built, as every web screen here is.

The pure rules — how a field is described, how values are grouped by character, who is in scene —
are in `lib/status.ts` with their own tests, the same ones the API's `render` has, because the strip
must name the characters the prompt will actually carry.

**Terminal.** One screen, opened with `T` from a story, is both the editor and the quick toggle: a
`[x]` per field (Space or Enter), the starters (`[+]`, Enter adds), the pins, and the values,
each editable in place. `A` takes a typed line — `Label`, `scene: Label`, or `Label = Low, High`
for a word list — which is parsed by a small pure function, `parse_new_field`. The new-story form
gets a *Status* row after the persona, reachable with Tab; Enter on the persona still starts the
story as it always did, because an extra Enter for everyone is a poor price for an optional row.

One bug is worth keeping. The first rendering of a field row printed no box at all: in Textual's
markup `[x]` is a **tag**, and an unknown tag is swallowed silently. The fix is to escape the
bracket (`"\\[x]"`), and the test that found it asserts on the *drawn text*, not on the state
behind it. A UI test that checks only the model it was built from cannot see a widget that draws
nothing.

## What the work taught

- **Derive state; do not log it.** Everything that could make the state wrong — a reroll, a cut, a
  branch — is the transcript changing, and the transcript is already the source of truth. One
  function that rebuilds from it replaces an undo for each case. The price is one thing that cannot
  be derived (what a person typed), and that one thing carries a flag.
- **Say a format twice, and put one of them last.** Chapter 7's lesson, applied: the format lives in
  a trailing layer, not in the card.
- **Bound what you send by who is in the room.** A prompt that grows with the size of the cast is a
  prompt that stops working at the size of the cast the owner actually has.
- **A response that is the whole state** is cheaper to build a client against than any patch
  protocol, and it is what made the two clients agree.
- **Keep the old behaviour of the one key people already press.** Enter on the persona still
  creates the story. The new row is there for whoever wants it.
