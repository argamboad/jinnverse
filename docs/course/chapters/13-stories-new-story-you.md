# Stories, new story, You

Step 12 built the room the story lives in. This step is the three screens around it — the list you
open it from, the form you start one on, and the page that says who you are and what it has cost —
and it is smaller and plainer than the last: three screens and one field of API. What it teaches
is how little a screen needs once the data is right: most of the work was deciding what the
*server* should say and what the *client* should work out.

## A count the list needed

The mock puts a line under each story's name: *Mara Vell · as Rowan · turn 7*. The list already
had the names; it did not have the turn. The story screen computes "turn 7" from the messages it
has loaded, but the list never loads messages, and loading every story's transcript to print a
number would defeat having a list.

So the list's row gained one field, `turns`, counted in the database next to the newest message:

```python
turns = (
    select(func.count())
    .where(Message.story_id == Story.id, Message.deleted_at.is_(None), Message.role == Role.USER)
    .scalar_subquery()
)
...
turns.label("turns"),
```

A **scalar subquery** is a query that returns one value and sits in the select list: for each
story row, the database runs it with that story's id. It is the same shape as the `LATERAL` join
that fetches the newest message in the same function, and for the same reason — one round trip
for the whole list, whatever the number of stories.

::: dotnet
In EF Core this is `Select(s => new { s.Name, Turns = s.Messages.Count(m => m.DeletedAt == null &&
m.Role == Role.User) })`: a navigation collection counted inside a projection, which EF turns into
a correlated subquery. Reading `story.Messages.Count()` in a loop instead is the N+1 that this
avoids.
:::

What counts is the **reader's** visible turns, not messages. A character's opening is a message
and is not a turn; a turn cut back is hidden and no longer counts. That is also what makes "not
started" mean something: a story that holds only an opening has zero turns, and the list says so
and shows no preview rather than quoting the opening as if it were the story. The test builds
exactly that — an opening, two turns, a reply, a cut-back turn, and a second story with only an
opening — and asserts `2` and `0`.

The line itself is *derived*, not stored: a pure function in `storyList.ts` joins the character,
`as` the persona (left out when there is none), and either `turn 7` or `not started`. It is a
function so that it can be tested without a browser; the screen only prints it. When the story
screen finishes a turn it refreshes the list's copy of `turns` too, from the same messages, so the
list does not say `turn 6` until the next fetch.

## Choosing, not selecting

The new-story form used a `<select>` for the persona and a column of cards for the character —
two ways to pick from a list on one screen. Now both are the same gesture. Characters are a strip
of cards, personas are rows, and each is a **radio group** in the accessibility sense: a container
with `role="radiogroup"`, buttons with `role="radio"`, and `aria-checked` on the one chosen. The
state is one variable each (`characterId`, `personaId`) and the styling reads it:

```svelte
<button role="radio" aria-checked={personaId === value} onclick={() => (personaId = value)}>
```

```css
.row[aria-checked='true'] { border-color: var(--gold); box-shadow: 0 0 0 3px var(--gold-soft); }
```

Selecting by the attribute means a screen reader and the stylesheet agree about what is picked,
because they are reading the same thing. The persona rows are drawn by a `{#snippet row(...)}`
declared once at the bottom of the file and rendered for the default persona and for each of the
others.

::: dotnet
A snippet is a `RenderFragment<T>`: a template held in a variable and invoked with arguments
(`@row(persona, "", true)`), local to the component. It is the right size for "this markup three
times in one file" where a whole child component would be a file for nothing.
:::

One value deserves a note. `personaId` is the empty string for *the default persona*, not the
default persona's id. A reader who never touches the persona gets whatever the library's default
is **when the story starts**, which is what the server does with `persona_id: null`. Sending the
default's id would pin the story to that persona even if the default later changed. The default
row is first, with a "default" chip, and the button names whoever will play:
*Start with Mara Vell as Rowan*.

### Reading what the character opens on, once

Under the cards, a line shows what the picked character opens on, in the book face. The list of
characters does not carry the opening (it carries a preview of the card), so the page fetches the
full entry when a card is first picked and keeps it in a record keyed by id. Picking back to a
character it has already read costs nothing; a failed read stores `null` and the line is simply
absent. The cache is a `$state` object, so writing `openings[id] = …` updates the line.

The mock drew a one-line opening; the real ones are five paragraphs, and the first version pushed
*As* and *Called* off the screen. The opening is rendered with the conversation's own `Prose`
(so `*action*` reads as action, not as asterisks) inside a box that shows its first lines and fades,
with *Show all* to let the rest out. A mock is a sketch of the data as well as of the screen; check
it against the real data before calling the screen done.

## Two scrolls and a foot

The form scrolls up and down; the strip of cards scrolls sideways; the Start button never scrolls.
Three things that want different overflow, and each is a rule you have to say out loud:

- The form's container is `overflow-y: auto; overflow-x: hidden`, so nothing the cards do can
  make the page wider.
- Only `.cards` is `overflow-x: auto`.
- The foot is not `position: sticky`; the form is a flex column, the fields area is `flex: 1;
  min-height: 0`, and the foot is a sibling after it. The foot stays because the area above it is
  the thing that shrinks — and `min-height: 0` is what lets it shrink at all (a flex child will not
  go below its content's height unless told it may).

## You, and what it is made of

You is a page of three cards and a line. Two of its facts need explaining.

**Who is signed in.** The client has only a token, so the name is read from it. A JWT is three
base64 parts, and the middle one is the claims; `tokenName` decodes it and returns `sub`:

```ts
const claims = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
```

This is for *display*. The client does not, and cannot, check the signature — it has no secret.
The API checks the token on every call. A token the client can read is not a token the client can
trust, and nothing here depends on it being true.

**The month.** "This month" is the spend report from the first of the month in UTC, which the
Stories bar used to show as a bare number. It now has the room for what the ledger already
knew — calls, what was rerolled away, how much of the prompt came from cache — and a *By story*
list that opens in place from the same report's `by_story`. `monthStart` is a pure function with
tests for the edges (a date on the last day of the year), because "the first of the month" is
exactly the kind of sentence that is wrong on the last day of December.

::: dotnet
Decoding a JWT without validating it is `JwtSecurityTokenHandler.ReadJwtToken`, as opposed to
`ValidateToken`. The first is for showing a name; only the second is for deciding anything.
:::

## What step 13 leaves behind

- The list says who each story is with and how far it has got, from one counted field.
- A new-story form that picks characters and personas the same way, shows what the story opens
  on, and starts from a button that does not move.
- A You screen that says who you are and what this month cost, with the cost taken off the
  Stories bar.
- Four more pure functions with tests (`whoLine`, `tokenName`, `monthStart`, `apiHost`).

**Next — Chapter 14, Library and editors.** Shelves with three tabs, a save bar for documents, a
history drawer, and the persona builder as a checklist.

## What the work taught

- **Ask what the server should count before asking what the client should show.** The line the mock
  drew needed one number the list did not have; the answer was a field, not a loop of requests.
- **A count is only as good as its question.** *Turns* is the reader's visible turns — not
  messages, not hidden ones — and "not started" falls out of that for free.
- **Pick the same way everywhere.** One gesture, one attribute, and the styling and the screen
  reader agree because they read the same thing.
- **A form that scrolls in two directions needs each direction said once**, and a footer that must
  not move is a sibling of the thing that shrinks, not a clever position.
- **A token you can read is not a token you can trust.** Show what it says; let the server decide
  what it means.
- **A dev server watches the files the checker writes.** Running `svelte-check` beside `vite dev`
  rewrites the generated files the server is watching and can leave it answering nothing; stop the
  server, run the gates, start it again.
