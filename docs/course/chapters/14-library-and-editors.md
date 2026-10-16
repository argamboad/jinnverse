# Library and editors

The last third of the redesign is the library: the shelves, the editors behind them, and the
persona builder. Chapter 12 settled one rule for the story — *settings save as you touch them* —
and promised its other half here: **documents save when you say so.** A card is written over
minutes and read by every story that uses it, so a half-typed sentence must not reach a story
because a field lost focus. This chapter is that half, plus the wide library that puts the
shelf and the editor side by side, and a builder that became a checklist.

It was six issues in one pull request, two of them found along the way.

## Ask the API before you draw

Two lines in the mocks needed data. *"v2 · in 3 stories"* under every row of a shelf, and
*"card v3"* beside the character in the story's column. Before building, the step started by
reading what the API already returned:

- The **card version** was there all along: every entry carries `version`, and a story always
  reads the newest. The story page reads the character's entry once and shows it (#198); no API
  change.
- **How many stories use an entry** was there only one entry at a time (`used_by`, a list of
  names, on the single read). A list of thirty characters cannot ask thirty times, so the list
  gained a count (#197), one grouped query for the whole shelf:

```python
rows = await session.execute(
    select(column, func.count()).where(Story.deleted_at.is_(None)).group_by(column)
)
counts = {key: n for key, n in rows}
naming_none = counts.pop(None, 0)   # stories that name no persona play as the default
```

The rule is the one `used_by` already followed, including its one subtlety: the default persona
is *used* by every story that names none, so its count adds that `None` bucket. A test builds a
default, a named persona, a story that names none and a deleted story, and asserts the counts
for all three shelves.

::: dotnet
`group_by` with `func.count()` is LINQ's `GroupBy(s => s.CharacterId).Select(g => new { g.Key,
Count = g.Count() })`, translated to one `GROUP BY` by EF Core. The `None` key is the group of
rows whose foreign key is null — what `GroupBy` gives you for a nullable key too.
:::

The third line could not be filled: *"v1 · built from 6 pieces"*. A persona built from pieces is
an ordinary persona once it is made — the builder copies the text in and records nothing about
how. Showing the number would mean a new column, a migration, and a value that would be blank for
every persona made before it. That is a product decision, not a technical one, so it was asked,
and the answer was to drop it. A mock is a picture of data as well as of a screen; when the data
is not there, the question goes to the person who owns the product, not into the code.

## The save bar

Every document editor — characters, personas, snippets, persona pieces — saves from one
component, `SaveBar`, which is not on the screen until there is something to save:

```svelte
{#if dirty || theirs}
  <SaveBar note={saveNote(one, used, version + 1, wide)} saveLabel={`Save as v${version + 1}`}
           disabled={!ready} onsave={save} ondiscard={discard} />
{/if}
```

`dirty` was already there: a `$derived` that compares each field with the entry as loaded. The bar
makes it visible. *Save as v4* says what a save does — it makes a new version — and on a wide
window the note says what that means for the stories: *the 2 stories using this persona read v2
from their next turn.* `saveNote` is a pure function with tests, like every sentence that counts.
*Discard* puts the loaded entry back into the fields, and the bar disappears because `dirty` is
false again; no extra state.

::: dotnet
This is a view model with `IsDirty`, and a toolbar bound to it with `Visibility="{Binding
IsDirty}"` — the same idea as `IEditableObject` with its `BeginEdit` / `CancelEdit` / `EndEdit`,
except the "original" is simply the object the API returned, kept beside the fields.
:::

### Leaving with changes

A save bar is a promise that unsaved work is not lost by accident, so leaving has to ask.
SvelteKit gives one hook for both ways out:

```ts
beforeNavigate(({ cancel, willUnload }) => {
  if (leaving || !dirty()) return;
  if (willUnload || !confirm('Leave without saving? Your changes will be lost.')) cancel();
});
```

A link or Back inside the app is a navigation the hook can cancel after asking. Closing the tab or
reloading is an *unload*: the page cannot show its own dialog, but cancelling it makes the browser
show its "Leave site?" — so the same `cancel()` covers both. `leaving` lets the editor's own exits
(after a save, after a delete) through without asking, which is why `guardLeaving` returns a
`leave(to)` that wraps `goto`.

::: dotnet
`beforeNavigate` is Blazor's `NavigationManager.RegisterLocationChangingHandler` (with
`context.PreventNavigation()`), and the unload case is the `beforeunload` event Blazor wires up
with `NavigationLock`'s `ConfirmExternalNavigation`.
:::

## Master and detail

From 900 px the library is a workspace: a rail on the left with the shelves and their entries,
and the editor beside it. It is the same shape as the story workspace in chapter 12, and it reuses
its lessons:

- **The rail is a component, the detail is a route.** `/library/characters/{id}` renders the
  editor; the rail is mounted beside it when the window is wide, and `/library` alone shows the
  rail and "Pick an entry, or write a new one". The URL is still the one source of truth for what
  is open, so Back, a bookmark and a reload all work.
- **One route, many entries.** Clicking another entry in the rail changes the route's parameter,
  not the page, so the editor reads the entry again in an effect on the id — chapter 12's
  "load on the parameter, not on mount", met a second time.
- **The rail follows, and refreshes.** It shows the shelf of the open entry, and a `stamp` prop
  (the entry's id, version and name) changes on every save, which makes the rail read its list
  again so the new name and version appear without a reload.

The rails of the two workspaces now share their head — the mark, the Stories / Library switch,
You — as `RailHead`, so the two sections look like one app.

The history of an entry, a sheet on a phone, is a drawer on a wide window: a third column that
opens beside the editor, so a reader can put an old version into the editor and compare it with
what is there before saving.

## A checklist and a sheet

The persona builder used to list every slot with its whole pool open under it: twelve slots, a
long scroll, and a die glyph that does not render on Windows. It is now a checklist. Each row is a
slot — or, for home, vehicle and pets, the three slots that write one paragraph together — with
what is picked, a *Random* that is a word, and a chevron. A row opens its pool in a sheet.

Which slots share a row is not a list in the client: the API's slots carry the paragraph they
write, and `groupSlots` puts consecutive slots of one paragraph in one row. The row's label joins
theirs, and its key joins their keys, so Svelte's keyed `{#each}` has a stable identity for it.

The sheet is driven by one piece of state — which row is open — and the picks apply as they are
tapped, exactly as before; *Done* only closes it. Writing a new piece closes the slot sheet, opens
the piece sheet, and on save reopens the slot sheet with the new piece picked. The persona itself
is one tap away under *Read it*, as the server joins it; the client still never assembles the
text.

## What step 14 leaves behind

- The library list counts the stories that use each entry; the story names its card's version.
- Three shelves on a phone, a pieces card under Personas, and the pieces as a route of their own.
- One save bar for every document, and a guard against leaving with changes.
- A wide library: rail, editor and a history drawer.
- A builder that is a checklist, with a slot sheet.

With this step the redesign's three milestones are done, and the app is ready for its next
deploy: the API first (it gained `turns` and `used`), then the web.

## What the work taught

- **Read the API before drawing a line that needs data**, and ask the owner before inventing data
  the product does not keep.
- **Settings save as touched; documents save when told.** The difference is how long they take to
  write and how many readers a half-finished one would reach.
- **Make dirty visible.** A save bar that appears only when there is something to save is a
  state indicator and a control at once.
- **One hook for both ways out.** In-app navigation and unloading the page are one event in
  SvelteKit; cancel it, and the browser asks when it must.
- **The detail is a route; the master is a component beside it.** The URL stays the truth, and
  the layout is a question of width.

## Postscript: what the staging review taught

The three steps were merged and deployed, and the owner opened staging with their real library
— fifty-three characters, names like *Anna Kistoff – Accidental Homewrecker*, cards that all
open with the same page of instructions — and sent six screenshots back. Eight things were wrong
that no dev server had shown, and they became one more small step (#200–#207). They are worth
a page, because every one of them is a kind of mistake a dev server lets you make.

**The same navigation on every screen.** The story and the library had become workspaces with a
rail; the Stories page and two library screens (the builder, the pieces) were still the centred
frame with the three pills. Each page had been correct on its own and wrong beside the others. A
redesign is not done screen by screen; it is done when the screens agree, and the only way to see
that is to walk the app, not the diff.

**Real data has a shape the mock did not.** The mock's names were two words; the owner's run to
forty characters and clipped in a field drawn at `1fr 1.4fr`. The mock's cards began with a
sentence about the character; the owner's all begin with the same preamble, so a preview of the
card's first words said nothing on fifty-three rows. The fix for the second was a rule on the
server — a character previews its *opening* when it has one — and that rule is now the TUI's
too, because both clients read the same field.

**A placeholder is copy.** "The innkeeper of the Gilded Heron" was the right hint for a character
and nonsense under a snippet; it had been typed once and rendered in three places. Copy that
depends on where it is shown is a value per place, not a string.

**A feature changes what other features show.** Step 11 made replies open with a status block;
nothing in Step 11 touched the story list, and the list's preview had quietly become
`📅 Day and time: …` on every story. The preview now starts where the prose does. When a step
changes the shape of a thing, look at every place that thing is read.

**Say "needed" once.** The builder lit a needed slot in the warning colour and, under it, offered
to leave it. Two parts of one row written at different times, each right alone.

And one lesson for the workshop rather than the product: `npm test` wedges the dev server exactly
as `npm run check` does, because vitest boots the SvelteKit plugin, which rewrites the generated
files the server watches. The order of work is now written down: edit, format, **stop the
server**, check and test, start it again, look.

::: dotnet
This is the difference between a passing test suite and a smoke test on a staging slot with
production-shaped data. The first proves each piece; only the second shows that the pieces are
one app. Keep a copy of real (anonymised) data for staging, and walk it after every deploy.
:::
