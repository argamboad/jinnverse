# The story workspace

Chapter 8 built the web app screen by screen: a list of stories, a conversation, and — behind a
◐ button — a page of dials and meters. It worked, and it asked the reader to leave the story to
change anything about it. A design review (a handoff of mocks, in `docs/handoff`) turned that
around: **the story is the room, and everything about it is in the room.** This chapter is the
first third of building it: the dials, the meters and the prompt beside the conversation instead
of on another page, the story's own actions under its name, the turn actions where a mouse or a
finger expects them, and on a wide window a workspace with three panes.

It was eight issues in one pull request, and it is mostly about one idea: **build a thing once,
and let the size of the window decide where it lives.**

## One body, two homes

The mock puts the dials in a column on a wide screen and in a sheet on a phone. It would have been
easy to write two components. There is one: `StoryRail` (a name from before this step; it is the
*panel*, not the list of stories) takes the story's `Extras` store and renders four tabs — Dials,
Meters, Status, Prompt. The column mounts it with `compact` set; the Dials sheet mounts it
without:

```svelte
<!-- the column, 1100 px and up -->
<StoryRail {extras} bind:section={panelTab} compact />

<!-- the sheet, below it -->
<Sheet bind:open={panelOpen} title="Dials" max="88%">
  <StoryRail {extras} bind:section={panelTab} />
</Sheet>
```

`compact` changes only what the narrow column needs: a shorter dial step with no label under it
(the level's name is the `title`), a lead line, and a body that scrolls on its own under fixed
tabs. The Status tab came from Step 11, after the mocks were drawn; it stayed as a fourth tab
rather than be dropped, which is the kind of decision a design handoff cannot make for you.

::: dotnet
This is a Razor component or a partial view rendered into two layouts, with a parameter
(`[Parameter] public bool Compact`) for the one difference. The page owns the state — which tab,
whether the sheet is open — and passes it down; `bind:section` is `@bind-Section`, a two-way
binding to a parameter, so the column and the sheet always show the same tab.
:::

### A dial the reader set, and one still following the card

A story has fifteen dials and most are never touched. Showing all fifteen as controls is a wall;
the mock shows the ones the reader *set* as controls and folds the rest into one line each, under
"Not set · following the card", that opens where it stands. The split is one field the API
already sent, `stored` (null until the reader sets it):

```ts
const setDials = $derived(enabledDials.filter((d) => d.stored !== null));
const unsetDials = $derived(enabledDials.filter((d) => d.stored === null));
```

A dial opened from the list gets a × that folds it away without setting it; once it is set it
moves up into the controls. That jump is the one thing in the screen that surprised me, and I
left it: the alternative, keeping a just-set dial in the list until the tab is left, needs state
whose only purpose is to hide the data's real shape.

### Optimistic, and honest about failing

The mock says dials, meters and names *save as you touch them*. Waiting for the API before the
control moves feels broken on a phone, so `Extras.setDial` changes the dial first and tells the
API second; if the API refuses, the dial goes back and a toast says why:

```ts
async setDial(key: string, value: string) {
  const before = this.dials.find((d) => d.key === key);
  this.replaceDial(key, (d) => ({ ...d, stored: value, effective: value, label: labelOf(dial, value) }));
  try {
    const changed = await api.setDial(this.storyId, key, value);
    this.replaceDial(key, () => changed);          // take the API's word for the rest
  } catch (error) {
    if (before) this.replaceDial(key, () => before); // and put it back
    toasts.show('danger', 'Not set', error instanceof Error ? error.message : undefined);
  }
}
```

The tests for it mock `api`, hold the call open with a promise that is resolved by hand, and
assert the screen's state *before* the promise settles — which is the whole claim. Meters (`setTracker`) and the story's name work the same way.

::: dotnet
Optimistic UI in a Blazor or WPF client is the same three steps: mutate the bound view-model
property, `await` the service call, and in the `catch` restore the old value and raise the error.
The restore is easy to forget, and it is the part a test should pin.
:::

## The window decides

Three layouts, one page: a phone (the bottom tabs, sheets), 900 to 1099 px (the centred 860 px
frame, with the Dials sheet), and 1100 px and up (the workspace: stories on the left, the
conversation, the column). CSS alone would do the *look*, but not the *work*: a rail that is
`display: none` is still mounted, still fetches the story list, and still gives the document a
second search box with the same id. So the page asks the window, in script:

```ts
const wideWindow = new Media(WIDE);      // '(min-width: 1100px)'
const wide = $derived(wideWindow.current);
```

```svelte
<div class={wide ? 'workspace' : 'screen'}>
  {#if wide}<StoriesRail current={id} />{/if}
  <div class="pane" class:wide> … </div>
  {#if wide}<aside class="column"> … </aside>{/if}
</div>
```

`Media` is a few lines over `createSubscriber`: the getter subscribes to the query's `change`
event while something is reading it, and lets go when nothing is. Svelte ships a `MediaQuery`
class that does the same, and it was not used for a small reason worth knowing: it wraps the
query it is given in one pair of parentheses, so a compound query such as
`(hover: hover) and (pointer: fine)` — *a mouse* — comes out malformed. `Media` takes the query as
written.

The mouse query matters for the turn actions. A phone has no hover, so a pill that appears
"when you hover a turn" would never appear, or would appear stuck on the last thing touched.
It lives in a media block instead, and the same block hides the "Hold any turn…" hint a mouse
does not need:

```css
@media (hover: hover) and (pointer: fine) {
  .hover { opacity: 0; transition: opacity 0.12s ease; }
  .msg:hover .hover, .msg:focus-within .hover { opacity: 1; pointer-events: auto; }
}
```

`:focus-within` is the keyboard's way in: the buttons are there, only transparent, so Tab lands on
them and the pill appears around the focus.

::: dotnet
`Media` is what you would write as a small JS-interop service in Blazor around `matchMedia`, or a
`SizeChanged` handler in MAUI: a boolean that re-renders its readers when the window crosses a
width. Conditionally rendering the rail (`@if (wide)`) rather than hiding it is the difference
between a component that exists and one that merely is not visible.
:::

## One page, many stories

The rail changes the story without leaving the page: `/story/A` to `/story/B` is the *same route
with a different parameter*, so SvelteKit keeps the component and does not run `onMount` again.
The page used to read its story in `onMount`, which was right while every story was a fresh
visit and wrong the moment the list sat beside it. The load moved into an effect on the id:

```ts
let shownId = '';
$effect(() => {
  const target = id;
  if (target && target !== shownId) {
    shownId = target;
    untrack(() => void openStory(target));
  }
});
```

`untrack` matters: `openStory` reads the URL and writes a dozen `$state` fields, and without it
the effect would subscribe to all of them and re-run itself on every change. Inside, the result of
each await is checked against the id *now* — `if (target !== id) return` — so a slow response for
the story the reader just left cannot overwrite the one they opened. The streaming call has the
same guard: an answer that finishes after the reader moved to another story is dropped rather
than appended to the wrong one.

::: dotnet
This is `OnParametersSetAsync` with a `CancellationToken` that is cancelled when the parameter
changes. Here there is no token, so the check is by hand: remember what you asked for, and ignore
the answer if the question has changed.
:::

## The list, extracted

The Stories screen and the rail show the same rows. The rows — the swipe, the confirm, the search
— moved out of the page into `StoryList`, with one prop, `rail`, for the tighter variant. On a
touch screen a row dragged left shows *Branch* and *Delete*; with a mouse the rail does not swipe
at all, and the same two buttons wait at the row's right end until the row is under the pointer.
Which of the two applies is the `Media(MOUSE)` query, so a laptop with a touchscreen gets whichever
device it is being used with at that moment.

The helpers the rows need (`initial`, `when`) are pure functions in `storyList.ts`, tested with a
fixed `now`; `when` takes the time as a parameter for that reason, with `Date.now()` as the
default.

## A file from a token

Export is the one thing in this step that is not about layout. The API already had
`GET /stories/{id}/export` and a `Content-Disposition` header carrying a file name. A web page
cannot simply link to it: the route needs the bearer token, which lives in a header the browser
does not send for a link. So the client fetches it, holds the blob, and hands it to the browser as
a download through a temporary anchor:

```ts
const url = URL.createObjectURL(blob);
const link = document.createElement('a');
link.href = url; link.download = name;
document.body.append(link); link.click(); link.remove();
setTimeout(() => URL.revokeObjectURL(url), 1000);   // revoking at once can cancel the download
```

And then a lesson about cross-origin pages: the file name was not there. A page on another origin
can read only the response headers the server *exposes*, and the API exposed none, so
`response.headers.get('Content-Disposition')` was `null`. It only bites where the web and the API
are different origins, which is the deployed arrangement. The
fix is one line, and the test asserts it, because nothing else would notice it stop:

```python
app.add_middleware(CORSMiddleware, …, expose_headers=["Content-Disposition"])
```

Until the API deploys with it, the client falls back to `transcript.md`, so the web can ship
first.

::: dotnet
`expose_headers` is `WithExposedHeaders("Content-Disposition")` on the CORS policy. Not exposing a
custom header is the most common CORS surprise: the request succeeds, the header is on the wire,
and `fetch` still cannot see it.
:::

## The slider and the debounce

A meter can be moved with a slider, and a slider fires `input` for every pixel it moves. Saving
each would be a request per pixel; saving only on release misses a keyboard. The panel moves the
value on screen at once and saves it 300 ms after the last touch, or at once when the card is
closed. The debounce is a dozen lines with a `flush` (leaving the card) and a `cancel` (removing
the meter), tested with fake timers so that "300 ms" is a thing the test controls rather than
waits for.

## The prompt, as a bar

The Prompt tab turns the audit line — `character 2,360 · world 417 · history 32 (1 dropped) …` —
into one stacked bar over the budget, so that *what the prompt was spent on* is a shape. The
arithmetic is small and lives in `audit.ts` where it can be tested: each layer's share is its
tokens over the budget (or over the total when there was none), and each segment fades a little
more than the one before so neighbours can be told apart. Under it, the list names the layers in
the order the code assembles them (`context.py`'s `ORDER`), with `history` shown as *recent
turns*, the dials counted under *directives* and the live facts under *world*.

Two chips sit at the bottom. **Facts** opens what the story believes, by subject. **Rebuild
memory** calls an endpoint that throws away the summaries and extracted facts and makes them again
from the transcript — many model calls, billed — so it asks first, in the panel, and says so.
A button that spends money confirms before it does.

## What step 12 leaves behind

- The story's dials, meters, status and prompt are one panel, in a column or a sheet, and the
  settings page is gone.
- A story's own sheet under its title: rename on blur, who it is with, what it has cost, branch,
  export and delete.
- A conversation that offers its actions where the device expects them, and a three-pane
  workspace from 1100 px.
- Optimistic dials, meters and names that put themselves back when the API refuses.
- `Media`, `StoryList` and the save-the-blob helper, which the next two steps reuse.

**Next — Chapter 13, Stories, new story, You.** The phone screens around the story: the list's
second line, a new-story form with cards instead of a `<select>`, and the month's spend moved to
You.

## What the work taught

- **One component, a parameter, two homes** is cheaper than two components that must be kept in
  step — until the parameter list starts to read like a second component.
- **Hiding is not the same as not rendering.** A `display: none` rail still loads, still has ids
  and still takes focus; ask the window in script and render only what is there.
- **Optimistic updates have a third step.** Change, call, and put it back; the last is the one
  that is skipped and the one a test can pin.
- **A route with a parameter is one component, not many.** Load on the parameter, not on mount,
  and ignore any answer to a question that has since changed.
- **A header on the wire is not a header in the page.** Cross-origin, the server decides which
  headers the page may read.
