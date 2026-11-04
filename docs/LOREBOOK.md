# Making a lorebook character

A character's card is sent whole, every turn. That is right for a card of a few thousand tokens
and wrong for a world of thirty thousand: the card alone fills the budget and the story has no
room to be remembered. A **lorebook** is the fix for that one case. Its entries are pieces of
the card moved out of it, each with the **keys** that bring it back in, and an entry is sent only
while one of its keys is in the scene.

This is the how-to. The design and the measurements are in chapter 20 of the course.

## Does this card need one?

Open the character's audit on any story that uses it (`GET /stories/{id}/audit`, or the story
page's audit panel) and read the `character` figure on a reply. The budget is 32,000 tokens by
default (`JINNVERSE_CONTEXT_BUDGET`).

- **Under about 10,000 tokens:** leave the card whole. The model reads it best in one piece, and
  nothing is gained. Fifty-two of the fifty-three cards on staging are here.
- **Above that:** the parts that only matter in some scenes become entries. *Blake Jameson
  University* was 26,606 tokens, 20,500 of them a cast of forty-seven. Split, its card is 3,878
  tokens and a scene with four people in it adds about 2,200.

A card without entries behaves exactly as before. There is no switch to turn on.

## What stays in the card, what becomes an entry

The card keeps everything the model must know in every scene: the world's introduction and tone,
the geography it needs to move people around, who it plays and who it never writes for, the
writing and behaviour rules, and anything short. Entries hold what is only needed when it is
present:

| Stays in the card | Becomes an entry |
|---|---|
| The world's introduction and tone | A character's full sheet |
| The campus, the town: where things are | A building or a place described in detail |
| The clubs and teams, as a list | A timetable or a schedule |
| The academic calendar, the holidays | A Greek house, a faction, an organisation |
| Who plays whom; how to write; how to behave | A menu, a set of shops, a district |
| A one-line **roster** of the cast | Anything the scene can do without until it is named |

**The roster matters.** With the sheets out of the card, the model would not know the cast
exists, and a card that says "let the world act, people arrive" needs it to. Keep one line per
character in the card — name, age, role, where they are found — and say that the full sheet
comes when they are in the scene. The BJU card's header lines ("Jacqueline Kai — 26, registered
counsellor at BJU, and the first face of this world") already were that roster.

Keep the always-present people in the card whole. A character who is in every scene does not need
to be fetched; the sheets that go out are the ones for people who appear when the story reaches
them. The same card can hold both, and a sheet can move back if the model keeps forgetting
someone who should always be there.

## Choosing keys

A key is a word or a phrase that, said in the scene, brings the entry in. Matching is on whole
words, in any case: `jax` matches "Jax's" and not "Jaxon"; `preston centre` is one key with a
space in it. Accents are not folded, so write a key the way the text spells it.

For a character's sheet, give it:

- the full name as it is said (`jacqueline kai`),
- the first name and the last name on their own (`jacqueline`, `kai`),
- every nickname (`sammy`, `lexi`),
- the role, when it is how people refer to them (`counsellor`, `the dean`, `lieutenant`).

For a place or a schedule, the names of the things in it and the words a reader uses to reach
it: a dining entry keyed on `lunch`, `dinner`, `coffee`, `hungry` and each restaurant's name; a
timetable keyed on `practice`, `tryout`, `game` and every sport.

**Avoid words prose uses for something else.** `rose` fires on "she rose from the chair",
`grant` on "I grant you that", `assistant` on anybody's assistant. A nickname that is also a
common word is better left out and the full name relied on. Two people sharing a name
(`sandra`, `jones`) both come in when it is said; that is usually right, since the model needs
to tell them apart.

Keys are kept lowercased and trimmed, without repeats; the editors take them on one line,
comma-separated.

## How an entry comes in, and goes out

- **In:** when one of its keys is a whole word in any of the **last six visible turns** (the
  reader's and the character's), or stands in the story's **status block** — the scene's place
  or time, or the name of a character the block is tracking. "Stallion Arena" in the place field
  keeps the arena's entry in for as long as the scene stays there, whether or not anyone says
  its name; "Friday" in the time field brings in a timetable keyed on `friday`.
- **Out:** six turns after the last mention, unless the status block still names it. A
  character stays through a short exchange about something else and goes once the scene has
  moved on.
- **Never from another entry.** An entry's own text is not scanned, so one sheet naming another
  person does not pull their sheet in. Only the scene does.
- **Under a cap.** All fired entries together may take `JINNVERSE_LORE_PERCENT` of the budget,
  20% by default (6,400 tokens of 32,000). When that binds, the most recently mentioned are kept
  and the rest left out; the audit says how many. Entries are sent after the history, in the
  order they were made, which is the order of the card they came from.

So make the entries in the card's order, and keep each to what one scene needs: a sheet of three
to six hundred tokens, a timetable of up to eight hundred.

## The steps

**Keep the original.** Make a second character for the split and leave the first as it is, so
the two can be played side by side and the audit compared. Create the second one with the full
card, then cut it down as you move pieces out, or paste the trimmed card in at the end.

**In the web app:** open the character's page in the library. Under the opening there is a
**Lore** section. *Add an entry*, give it a name (a handle for the list, never sent), its keys on
one line, and its text, then save it from its own buttons. Entries list in the order they were
made with their keys under the name; open one to edit it; the × deletes after a second click. A
save over an edit made elsewhere is refused with the other text shown, as a card's is.

**In the terminal client:** on the characters shelf, `L` opens the selected character's lore.
`N` asks the name, then the keys, then opens your editor on a skeleton; `Enter` edits the text,
`K` the keys, `F2` the name, `Del` removes after asking. The shelf's caption counts a
character's entries.

**Through the API:** `/library/characters/{id}/lore` — list, `POST` to create with `name`,
`keys` and `text`, `PATCH` an entry with the `version` the editor started from, `DELETE`, and
`/history` for its saved versions.

## Reading the result

Play a scene and open the audit. A reply now reads like:

```
character 3882 · persona 412 · history 6120 · lore 2211 · total 12625/32000
```

`lore` is what the scene's entries cost; `(2 dropped)` after it means the cap bound and two
fired entries were left out. The `history` figure is the number to compare against the original
card: it is how much of the story the model could still see.

If a character keeps arriving without their sheet, their keys are missing the word the story
uses for them: open the entry and add it. If a sheet keeps arriving when it should not, a key is
too common: take it out.
