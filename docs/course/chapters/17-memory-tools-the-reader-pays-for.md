# Memory tools the reader pays for

Step 19 ended with the owner rebuilding a long story's memory and reading the facts it came back
with. One hundred and nine of them, and "Alana Davis invited Allan to the ADP open house tonight
at 7:00 PM" was still among them two hundred turns after the evening, so every reply was told the
open house was ahead. The owner's question was a design: what if the app had a tool that reads the
whole fact list and proposes what to retire, billed like anything else that calls the model, as
long as the cost is shown first? Step 20 built that tool, a second one of the same shape for the
summaries, and fixed the extractor that had let the list grow that way. Six issues, one pull
request.

This chapter is about three things: why the world state only grew, how each figure was measured
on a real story before any code was written, and the shape every tool that calls the model on
request now shares.

## Why the world state only grew

The ledger said it first. Twenty-seven fact extractions on the story, and the `facts` table had
**zero retired rows**. The extractor is offered the live facts every time and may name any of
them as no longer true, and in twenty-seven chances it never did.

Two causes, found by replaying real extractions read-only through the same code. The first was
the rule. The instruction said *retire a fact only when the transcript actually contradicts it*,
and *be conservative*. Shown ninety-six facts including the invitation, and reading the stretch
where the open house happens, the extractor added three facts and retired none. A plan that
happens contradicts nothing: nothing in the transcript says "Allan was not invited". The rule
had no word for *fulfilled*, or for a state a newer one replaces, so the list could only
accumulate.

The second cause was quieter. Each fact was shown with the first eight characters of its id, for
the model to name it by:

```
01a155b4 | Allan Sanlucar El Kettani | hosts the BJU Radio show...
01a155b8 | Lupo | loves swimming in the pool...
```

The ids are UUIDv7, time-ordered: a timestamp first, randomness after. Facts extracted in the
same second share everything but the last character or two. Of the story's fifty-two live facts,
all shared one seven-character prefix, and only five eight-character prefixes existed between
them. A model cannot tell `01a155b4` from `01a155b8` reliably, and `retire()` needed a unique
match, so a near miss retired nothing and said nothing. A review probe later mis-attributed two
proposals exactly this way.

The fix is two lines of thought. The instruction now retires *a plan, invitation or appointment
that has since happened* and *a state a newer one replaces*, recording what it left true as a
new fact. And the facts are numbered, 1 to N, in the order the list is sent; the answer names
numbers. A number off the list retires nothing, as before, but now the model can count.

::: dotnet
UUIDv7 is what `Guid.CreateVersion7()` makes in .NET 9. It is the right primary key for a table
that is read in insertion order, and the wrong thing to show to a model, or a person, as a short
handle: the prefix carries the time, which is the same for everything made together. A grid
numbers its rows for the same reason.
:::

## Measure first, with the real story

Every number in this step came from a throwaway script in the session's scratchpad, reading the
staging database directly and storing nothing, before a line of application code changed. The
summary replays of Step 19 had set the habit; here it decided the design.

**A review of the facts alone cannot work.** The first draft sent the model the fact list and
the latest summary. It proposed rewriting the invitation into "is expected at the open house
tonight", and the reason was honest: *the open house is still upcoming*. The summaries stopped
at turn 303; the story was at 554, and the evening sat in the live turns the draft never sent.
A reviewer has to see what the reply model sees. The second draft composed the story's own prompt
(character, summaries, live history, the facts numbered in the instruction) the way `/ask` does,
and proposed exactly what the owner had asked for: *attended the Alpha Delta Pi open house on
Monday evening, brought a Nina Simone portrait, played the Fazioli*.

**Thinking off.** With the model's reasoning on, thirteen facts consumed all 8,000 tokens of the
ceiling and the answer was empty: the same failure Step 19 found in the summariser.

**A cap.** The first composed-prompt run made 19 proposals; after one rule was added it made 47
on 52 facts, rewriting nearly everything, adding "and has become a friend who follows his work"
where nothing said so. *At most twelve, the most important first; a fact that is still true as
written is not listed; each fact in at most one proposal* brought it to twelve, with the open
house first.

**Never a trait because the story shows it.** Among the nineteen, the model retired *plays
piano, guitar and sings*, *owns a custom Telecaster* and *is a lieutenant with the campus
police*, each with the reason that the summaries demonstrate it. That is backwards: the
summaries are compressed away over time, and these facts are what remains of them. One rule
names the classes that are never retired for being demonstrated.

**And a cost.** The composed prompt is the same size as a reply's, about 88,000 tokens on this
story, so a review costs what a reply costs: $0.003. The estimate shown before pressing is the
story's own average priced reply, read from the ledger.

For the summaries the measurement was shorter. The seven summaries the rebuild had made,
5,090 tokens between them, were sent closed off in tags with the summariser's own instruction and
"at most 700 words", and came back as one account of 1,058 tokens: a fifth of the room, every
name, time and open thread still there, for $0.0004. That was enough to build on.

::: warning
A prompt that works on one run is not a prompt that works. Three of these rules came from the
second and third replays, each fixing what the previous one did too eagerly. The per-proposal
confirm is the real guard: the reasons are shown to be judged. But a model that proposes 47
changes exhausts the judge.
:::

## The shape

Both tools, and Rebuild memory before them, now share one shape, and it is the shape anything
that calls the model on request should take here:

1. **A dry run with an estimate.** `POST …?dry_run=true` makes no call and answers with what
   would happen and what it would cost, from the ledger. The client shows the number in the
   confirm: *One call, about $0.0031*.
2. **One billed call, written to the ledger before it is judged**, with a new kind: `review`,
   `condense`. Two migrations widen the CHECK on `spend.kind`, because a ledger that refuses an
   unknown kind is doing its job.
3. **Propose, don't apply.** The review answers proposals and changes no fact. `parse()` is
   strict the way the extractor's is: a number off the list, a pinned fact, a fact already taken,
   a retire with text or a rewrite without, a merge of one — dropped and counted, never guessed.
4. **The reader confirms, then apply as one.** `POST …/review/apply` takes the kept set back and
   runs it in one transaction: a fact pinned or retired meanwhile refuses the whole set, since
   the reader confirmed it against the list as it was.

```python
async def apply(session, settings, story, confirmed):
    live = {fact.id: fact for fact in await facts.live_facts(session, story.id)}
    at = await facts.newest_sequence(session, story.id)
    for proposal in confirmed:
        sources = [live.get(fact_id) for fact_id in proposal.fact_ids]
        if any(fact is None or fact.pinned or fact.id in seen for fact in sources):
            raise HTTPException(409, "…Review again.")
        for fact in sources:
            fact.valid_to_sequence = max(fact.valid_from_sequence, at)
        if proposal.text is not None:
            session.add(facts.add(story, subject, proposal.text, at, model=settings.model))
    await session.commit()
```

A rewrite or a merge retires its sources and adds the new sentence as a model-written, unpinned
fact: the model proposed it and a person only agreed, so the extractor may retire it later like
any other. Retiring never deletes; the row keeps the turn it became true and the turn it stopped.

Condense has the same four steps with one wrinkle in the fourth. The new summary spans the first
old one's starting turn to the last one's end, and `(story_id, from_sequence)` is unique. The
unit of work flushes inserts before deletes, so adding the new row and marking the old ones
deleted in the same session fails on the constraint. The old rows are deleted with an explicit
statement first, then the new one is added, still inside one transaction.

::: dotnet
This is EF Core's `SaveChanges` ordering: inserts, then updates, then deletes, topologically
sorted by foreign keys — not by the unique indexes you happen to have. The cure is the same:
`ExecuteDeleteAsync` for the rows that must go first, inside the transaction, before `Add`.
The dry-run/apply pair is the preview–commit shape of an `IDbContextTransaction`: everything is
computed and shown, nothing is durable until the reader says so.
:::

## Two clients, again

The terminal client got `/review` and `/condense` as local commands in the same step, with the
same four beats: the dry run, the confirm screen with the price, the call, and for the review a
pane that lists each proposal with a switch (`Space`), `A` to apply the kept ones, `Esc` to apply
none. Its keys are in help under the drift test from chapter 16. The web got two chips beside
*Rebuild memory*, each opening its confirm with the number, and a sheet of proposals with a
switch per card, approved on a mock in both themes before it was built and checked in the
browser after.

One detail from the terminal that is worth a line: Textual's `DOMNode` already has an
`action_toggle(attribute_name)`. A screen that defines `action_toggle(self)` for its own Space key
overrides it with the wrong signature, and pyright says so. The pane's action is
`keep_or_drop`.

## What this step teaches

- **A ledger finds bugs.** Zero retirements in twenty-seven calls, and 47 of 81 summaries
  sitting exactly on a ceiling (Step 19), were both read off `spend` before anyone read a line of
  prose. Count what the model does, not only what it costs.
- **Show the model what the decider sees.** A reviewer of the facts needs the story the facts
  are about; a summary of summaries needs them in order and closed off. Context is the design.
- **Measure before you build, on the real thing, and three times.** The rules that make the
  review usable came from its second and third replays. A guess at any of them would have shipped
  a different wrong number.
- **Propose, confirm, apply as one.** The shape costs a dry run and an apply endpoint, and it
  turns a model's guess into something a person signed. Every tool here that spends money takes
  it from now on.
