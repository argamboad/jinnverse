# Persona pieces

The roadmap ended at step 9, and then the owner asked for something the first nine steps made
easy: a persona built from parts. Every chat can have its own persona, but writing one by hand
means copying three thousand characters of prose and editing them. This chapter is the feature
that came after: a pool of **pieces**, a **joiner** that turns a pick into a persona, a way to
**extract** the pieces from the personas that already exist, and a picker in each client. It was
five issues in one pull request (with a fix to the memory, below), and it taught three things worth a chapter: a **closed
vocabulary** (an enum the database also enforces), a **pure function at the centre** with the
side effects around it, and a **proof by round trip** that a refactor of data did not break its
format.

It also changed one earlier thing. A reader of chapter 6 will find a paragraph there about turns
the context builder dropped before any summary covered them. That was found while this feature was
being planned, from the same story's diagnostics, and is fixed in `compose`; it belongs to the
memory, so it is told there.

## The persona does not change

The first decision was what *not* to build. A persona is a name and a page of text, a story
points at it by id, and editing it reaches every story that uses it (chapter 4). The prompt
builder takes it as plain text (chapter 5). Everything that touches personas — search, export,
the default persona, the version history — would have to change if a persona became a structure.

So it did not. The pieces are **an authoring tool**: they build the text, once, and the text is
copied into an ordinary persona. Editing or deleting a piece later changes no persona already
made, because no persona refers to a piece.

::: dotnet
This is the difference between a *composed* object and an *assembled* one. In .NET terms the
persona is a plain entity and the pieces are a builder: `PersonaBuilder.Build(picks)` returns an
entity, and nothing keeps a reference to the builder's inputs. The alternative — an entity made
of references to pieces — would make every read a join and every edit a change to someone else's
prompt.
:::

## A closed list of slots

The owner's six personas share one skeleton: nine paragraphs, always in the same order — identity
and look, style, marks, family, work, home, personality, humour, passions. The pieces are slotted
by that skeleton, plus the slots the owner added (a vehicle, pets), and **the list of slots is
closed**. There are no user-defined categories. A persona has to come out in the card's format,
and free text dropped into a persona may be ignored or overused by the model; a fixed list makes
every persona the same shape.

A closed list is an enum, and an enum here is two things at once:

```python
class PieceSlot(StrEnum):
    NAME = "name"
    LOOK = "look"          # identity and look, with the style and the marks
    FAMILY = "family"
    WORK = "work"
    HOME = "home"
    VEHICLE = "vehicle"
    PETS = "pets"
    PERSONALITY = "personality"  # with the humour and the passions
```

Eight slots, not twelve: the first version gave the style, the marks, the humour and the passions
a slot each, and the section at the end of this chapter tells why they folded into the look and
the personality, and how a closed list changes once rows exist.

The **declaration order is the persona's paragraph order**: a client that lists the slots in
this order shows them in the order the text will read. The same list is written a second time,
as a `CHECK` constraint, because the database should refuse what the code would never write:

```python
class PersonaPiece(LibraryEntry, Base):
    __tablename__ = "persona_pieces"
    __table_args__ = (
        Index("uq_persona_pieces_slot_voice_name_lower",
              "slot", "voice", text("lower(name)"), unique=True),
        CheckConstraint("slot IN ('name', 'look', …, 'passions')", name="slot"),
        CheckConstraint("voice IN ('he', 'she', 'they', 'any')", name="voice"),
        CheckConstraint("(slot = 'name') = (short IS NOT NULL)", name="short_only_for_names"),
    )

    slot: Mapped[PieceSlot] = mapped_column(_stored_as_text(PieceSlot))
    voice: Mapped[Voice] = mapped_column(_stored_as_text(Voice))
    text: Mapped[str] = mapped_column(Text)
    short: Mapped[str | None] = mapped_column(String(100))
```

Three things to read in it. `LibraryEntry` is the mixin from chapter 4: `PersonaPiece` gets its
id, its name, its version and its time of last change for nothing. `_stored_as_text` is the enum-as-text
helper in `models.py`, so the table holds `'home'`, not a number. And the third `CHECK` is a
**biconditional**: `(slot = 'name') = (short IS NOT NULL)` says a piece has a short form *if and
only if* it is a name piece. Two booleans compared with `=` is how SQL writes "both or neither".
The index is unique per slot, voice *and* name, case-insensitively: "Penthouse" may exist once for
a he persona and once for a she persona.

::: dotnet
`StrEnum` is an `enum` stored as its string name — `HasConversion<string>()` in EF Core — and the
`CHECK` is `HasCheckConstraint`. The migration (`0016_persona_pieces.py`) is the same table in
Alembic's vocabulary, and `test_the_migrations_build_exactly_what_the_models_describe` fails
when the two disagree.
:::

## The joiner

Everything the feature knows about the persona's shape is one pure function and two constants.
`PARAGRAPHS` says which slots write which paragraph:

```python
PARAGRAPHS: tuple[tuple[PieceSlot, ...], ...] = (
    (PieceSlot.LOOK,),
    (PieceSlot.FAMILY,),
    (PieceSlot.WORK,),
    (PieceSlot.HOME, PieceSlot.VEHICLE, PieceSlot.PETS),
    (PieceSlot.PERSONALITY,),
)
```

Home, vehicle and pets share one paragraph, their sentences joined with a space, because that is
where the owner's personas keep them: "He lives in a penthouse. He rides a Royal Enfield." is one
paragraph. Every other slot writes paragraphs of its own, and a piece may hold more than one: a
look piece is three (the look, the style, the marks), a personality piece up to three, and the
work slot has two in one of the personas. `assemble` walks the groups:

```python
def assemble(picks: Mapping[PieceSlot, Sequence[PersonaPiece]]) -> str:
    names = picks.get(PieceSlot.NAME, ())
    if len(names) > 1:
        raise PieceError("A persona has one name.")
    paragraphs: list[str] = []
    for group in PARAGRAPHS:
        texts = [piece.text.strip()
                 for slot in group for piece in picks.get(slot, ()) if piece.text.strip()]
        if len(group) == 1:
            paragraphs += texts           # one paragraph a piece
        elif texts:
            paragraphs.append(" ".join(texts))   # home, vehicle and pets: one paragraph
    if not paragraphs:
        raise PieceError("Pick at least one piece.")
    text = "\n".join(paragraphs)
    …
```

Empty slots are skipped, which is how the roommate persona — the same person with no home
paragraph — is just a pick with no home piece. The order of the *pick* does not matter, only the
order of `PARAGRAPHS`. And the function takes ORM objects and touches no session, so its tests
build `PersonaPiece(slot=…, text=…)` in memory and call it, with no database.

::: dotnet
A static method over an `IReadOnlyDictionary<PieceSlot, IReadOnlyList<PersonaPiece>>`: no service,
no interface, no DI. The rule from chapter 7 — pure functions at the top of a module, the few
`async def` that touch the database under them — is why the joiner is easy to test and why the
two clients cannot disagree with it: neither client joins anything.
:::

### The name, written twice

Fourteen of the fifty-seven paragraphs in the owner's personas name the persona, and not only
the first: "Allan Sanlúcar El Kettani is an athletic young man…" opens the look, and "Allan is the
son of…" opens the family paragraph. A piece that hard-codes "Allan" would carry the wrong name
into another persona. So pieces write the name as a placeholder, and there are **two**, because
the text uses two forms: `{name}` for the full name and `{short}` for the short one it uses after
the first mention. The name piece carries both (its text is the full name, its `short` column the
short form — the reason for that `CHECK`), and `assemble` fills them in. A piece that asks for a
name when none was picked is refused with a sentence that says so.

### The voice, and what was not built

Every one of the six personas uses *he* and *his*. Someone will want a female persona, and the
tempting answer is placeholders for the pronouns: `{he}`, `{his}`, `{him}`. It does not work.
English pronouns are not a substitution: "his" is "her" in "his sister" and "hers" in "the bag is
his"; "He's" and "himself" and the capital at the start of a sentence all have their own rules;
and a female persona needs different *content* anyway — body, clothes, tattoos.

So each piece carries a **voice**: `he`, `she`, `they`, or `any` for a piece with no pronouns in
it. The builder asks for the persona's voice first and offers only the pieces written in it (or
in none), and the server refuses a pick that mixes them. A female pool is a set of pieces written
in *she*, tagged *she*. There is no conversion step because there is nothing to convert.

## The API, and what it reuses

Seven endpoints under `/persona-pieces`: the slots (so a client does not hard-code them), the pool
by slot and voice, create, save, delete, and the two that matter — **preview** and **build**. Both
take the same body (a voice, the picked ids by slot, optionally a name) and both run the joiner;
preview returns the text and the name the persona would get, and saves nothing. The clients call
it on every change, which is why the web and terminal previews cannot differ from what is saved.

Build makes an ordinary persona, and it does so by the library's own path. `create_entry` used to
hold the rules for adding a persona to a shelf — a name already there is refused, the first
history row is written, the database's `updated_at` is read back. Rather than copy them, they
became `add_entry(session, shelf, name, text)`, and both endpoints call it. The commit that did it
changed no behaviour and the library's tests did not notice.

The persona's name is the one thing the joiner cannot decide, because names are unique:

```python
async def free_name(session: AsyncSession, wanted: str) -> str:
    """`wanted`, or `wanted-2`, `wanted-3`… the first no persona has, in any case."""
```

It is suggested from the name piece as a *slug* — `unicodedata.normalize("NFKD", …)` and the
ASCII letters only, so "Allan Sanlúcar El Kettani" becomes `allan-sanlucar-el-kettani`, like the
owner's other persona names — and numbered when taken. A name *given* in the request is used as it
is and refused with a 409 when taken: a person who typed a name should be told, not renumbered.

The refusals deserve the same attention as the successes. `PieceError` is a plain `ValueError`
the pure code raises; the endpoint turns it into a 422 whose body is the sentence. That is the
usual split — the domain says what is wrong, the transport decides the status — and it is why
a screen can show the server's own words ("'Her look' is written in the she voice; this persona
is he.") without translating anything.

::: dotnet
`PieceError` is a domain exception caught in one place and mapped to `ProblemDetails` — an
exception filter, or `app.UseExceptionHandler` with a switch on the exception type. FastAPI has no
filter pipeline; the `try` around `assemble` in the handler is the whole mechanism.
:::

## Extracting the pieces that already exist

Typing six personas back in as pieces would be pointless and would drift from what works. The
owner's personas are the most trustworthy source of pieces there will ever be, so the feature
reads them: `scripts/extract_persona_pieces.py`, run like `seed_dummy.py`.

The rules for a paragraph are simple, deliberately, and there is no model call:

```python
RULES: tuple[tuple[PieceSlot, re.Pattern[str]], ...] = (
    (PieceSlot.LOOK,  # the marks
     re.compile(r"^(his|her|their)\s+(tattoos?|scars?|piercings?)\b", …)),
    (PieceSlot.PERSONALITY, re.compile(r"^(his|her|their)\s+humou?r\b", …)),
    (PieceSlot.PERSONALITY,  # the passions
     re.compile(r"^(his|her|their)\s+(passions|interests|hobbies)\b", …)),
    (PieceSlot.HOME, re.compile(r"\b(lives? in|penthouse|apartment|…|rides an?)\b", …)),
    (PieceSlot.FAMILY, re.compile(r"\b(son of|daughter of|sister|brother|twin|…)\b", …)),
    …
)
```

The first paragraph is always the look, the first rule a paragraph matches decides its slot, and
the work slot takes what is left. In the look and the personality, paragraphs that follow each
other become **one piece**, a line break between them, which is how a look piece comes to hold
the style and the marks; every other slot keeps a piece a paragraph, so a builder may pick the
parents without the twin. A model would have been more flexible and less honest: it would
have answered confidently when the rule did not hold, and it would have cost a call per paragraph
and given a different answer on a re-run. A rule that is wrong is wrong the same way every time,
and the next step catches it.

That step is the **proof**. A persona is saved as pieces only when its pieces, given to the joiner,
return its text *exactly*:

```python
def rejoins(self) -> bool:
    try:
        return self._rejoined() == self.original.strip()
    except PieceError:
        return False
```

If the suggestion is wrong in a way that changes the order — a work paragraph taken for a
personality one — the joiner puts it elsewhere and the comparison fails, and the persona is left
out and named. The first run on the owner's six personas is the example: **three of six did not
rejoin.** The tattoo rule was `\btattoo`, and the paragraph "His twin sister, Macarena, is a gifted
visual artist and tattoo artist." matched it and became a marks paragraph, which sits in the
joiner's order *before* the family one. The fix was to anchor the rule to paragraphs that *start*
with "His tattoos", and the second run rejoined all six, the roommate variant included. Without
the proof, that bug would have shipped as a persona whose sister paragraph came out in the wrong
place.

Around the rules: a paragraph several personas share (they share most of them) becomes **one**
piece, because pieces are keyed by `(slot, voice, text)` and an existing one is reused, which also
makes a second run add nothing; the persona's own name is replaced by the placeholders; every piece
is tagged `he`; and the persona itself is only *read*. The owner confirms each persona in a
review, and that review is written so it can be tested without a terminal:

```python
def review(plan: Plan, ask: Callable[[str], str], say: Callable[[str], None]) -> bool:
```

The script passes `input` and `print`; a test passes a list of answers and a list to collect what
was shown. `--dry-run` shows the plans and writes nothing, and `--yes` accepts every suggestion
that rejoins.

::: dotnet
`ask` and `say` are `Func<string, string>` and `Action<string>`: the seam where .NET code would
take an `IConsole` or a `TextReader`/`TextWriter`. Injecting two callables instead of an interface
is the Python habit for a seam this small, and a lambda in a test is the whole fake.
:::

## The two clients

Neither client knows how a persona is joined; they choose, and they ask the server to show them.

**The terminal** (`tui/src/jinnverse_tui/builder.py`) has the slots down the left and the pool of
the selected slot on the right, the preview underneath. `Space` picks, `N` writes a new piece in
the editor, `V` changes the voice, `R` picks at random, `Ctrl+S` names the persona and makes it. It
opens from the library (`B`) and from the new-story form (`Ctrl+B`), and tells the screen that
opened it which persona was made, so the library selects it and the form picks it. Its tests run
against the same fake server as the rest of the client, which gained the pool and the two join
endpoints with the API's own rules in the small.

**The web app** (`routes/library/personas/from-pieces`) is one card per slot in a column, with the
pool opening under the slot, a sheet for a new piece, and the preview as the server's own join,
asked again a moment after the pick stops changing. The design was shown to the owner in dark and
light before it was built, as every screen is. A small thing worth knowing: the route is
`from-pieces` and not `build`, because the repository's `.gitignore` ignores any folder called
`build` — a page named that was never committed, which `git status` showed by not listing it.

Both ask for the same minimum, and it is the one rule that lives in the screens and not in the
API. The API needs one piece. The screens need a **name** and a **look**: every persona opens with
them, and a piece that writes the name needs a name piece. A slot with nothing picked says
"needed" or "None picked — optional", and making a persona without the needed ones says what is
missing instead of failing. Keeping the rule out of the server is deliberate: anything else that
uses the API is not bound by what these two screens think a persona should have.

## Reading and editing the pool

The first version of the pieces could be picked, written in the builder and deleted through the
API, but not read whole or changed: the builder showed a piece as a few lines of its text, and
the API's save had no client. The owner had thirty-six pieces and nowhere to see them. The
second pass gave them a shelf and an editor in each client, and a description like the other
shelves'.

**The shelf.** The library gains a fourth tab, *Pieces*, with its count. The pool is listed in the
persona's own slot order, then by name; a row is the name, the voice, and the description when
there is one, falling back to the start of the text. A piece has no history (a persona built from
it keeps its own text, so an old version of a piece is not lost the way an old persona is), and
the slot cannot change: moving a piece to another slot would change what it means.

**The editor.** It shows the whole text with `{name}` and `{short}` as written (and two buttons
that insert them), the voice, the description with a counter, and for a name piece the full name
and the short form. A save carries the version it started from, and a save over a change made
elsewhere shows the piece as the server has it now and lets the owner replace it or take it —
the same conflict as the other shelves, because the API's 409 carries `current` for pieces too.
Deleting asks first and says that personas already built keep their copy.

**The terminal client's trick.** The library screen is written for entries: a name, a text, a
version. Rather than teach it a second kind of thing, the API client maps a piece *onto* an entry
(`PieceEntry`, an `EntryFull` with the slot and voice beside it, named "Home · Penthouse (he)") and
routes `entries`, `save_entry` and `delete_entry` to `/persona-pieces` when the shelf is
`pieces`. The screen then needs only the pieces' own keys — `V` for the voice, `S` for a name
piece's short form, `N` asking for a slot and a name. It is the adapter pattern: the screen keeps
one model and the client does the translation. There is also no endpoint for one piece, only the
pool, so the list carries each piece's whole text and the shelf makes no call per row.

**The web client's trick** is smaller. Leaving the builder for the editor would lose the pick,
which lives in the page's memory. The builder writes its pick to `sessionStorage` on every
change (for this tab only), reads it back when it mounts — putting back any piece that was
deleted or is in another voice meanwhile — and forgets it once the persona is made. An editor
opened from the builder carries `?back=builder`, and Back returns there.

## Testing it

- **The joiner is tested as a function:** order, an empty slot, the home paragraph, more than one
  piece in a slot, a piece with more than one paragraph, the placeholders, the refusals.
- **The API through `client`:** the pool, the version conflict, a name taken in one voice and not
  in another, a preview that saves nothing, a build that makes an ordinary persona with its history
  row, a number added to a taken name, and — the test that states the whole design — that editing
  or deleting a piece afterwards leaves the persona as it was.
- **Extraction on an invented persona**, so no one's real text is in the repository, including the
  end-to-end acceptance: pick a persona's pieces in its own order, call the real build endpoint,
  and get its text back exactly.
- **The clients:** the terminal on its fake server, headless through Textual's pilot; the web
  app's rules, which need no screen (what is needed, toggling, keeping a pick across a change of
  voice), as plain Vitest tests in `lib/personaBuilder.spec.ts`.

::: try
Look first, write nothing: `uv run python scripts/extract_persona_pieces.py --dry-run` against
your own database shows each persona's paragraphs with the slot suggested for each, and whether
the pieces would give the persona back exactly. Then run it without the flag and answer the
review. Open the web app's library, the Personas shelf, **Build from pieces**; pick a name and a
look, and watch the preview change as you add a home and a pet. In the terminal, `uv run
jinnverse-tui`, the library, `b`. Change the voice and see the pieces written for the other one
appear.
:::

## What this leaves behind

- A pool of pieces in fixed slots and a joiner that builds a persona in the exact format of the
  ones that already work, with the persona still plain text.
- A way to turn existing personas into pieces that proves, for each, that nothing was lost.
- A picker in each client, with one rule — a name and a look — that lives in the screens.
- A shelf and an editor for the pieces themselves, with a description, in both clients.
- Two decisions to note. The slot list is closed on purpose, and the voice is a tag on a piece,
  not a substitution in the text.

## Fewer slots: how a closed list changes (Step 22)

The twelve slots came from the skeleton, one slot a paragraph, and that was the mistake: the
owner, curating the pool a week later, found twelve rows too many to pick through, and three of
them — the look, the style, the marks — never picked apart from each other, nor the personality,
the humour and the passions. So four slots folded into two (#254), and the look piece became
three paragraphs, the personality piece up to three. The joiner did not change: a piece could
already hold more than one paragraph, and `PARAGRAPHS` only lost four groups.

What a closed list costs shows here. The enum is written in three places — the Python class, the
`CHECK` constraint, and the rows that already carry a slot — and the first two cannot shrink
while rows in the third would fail the new constraint. So the change is a **migration that moves
data**, not an edit:

```python
ABSORBED = {"style": "look", "marks": "look", "humour": "personality", "passions": "personality"}

def upgrade() -> None:
    connection = op.get_bind()
    moving = connection.execute(sa.text(
        "SELECT id, slot, voice, name FROM persona_pieces "
        "WHERE slot IN ('style', 'marks', 'humour', 'passions')")).all()
    for piece_id, slot, voice, name in moving:
        new_slot = ABSORBED[slot]
        connection.execute(sa.text("UPDATE persona_pieces SET slot = :new_slot, name = :name "
                                   "WHERE id = :id"),
                           {"new_slot": new_slot,
                            "name": _free_name(connection, new_slot, voice, name),
                            "id": piece_id})
    op.drop_constraint("ck_persona_pieces_slot", "persona_pieces", type_="check")
    op.create_check_constraint("ck_persona_pieces_slot", "persona_pieces", f"slot IN {NEW}")
```

Rows first, constraint last, and the unique index of (slot, voice, lower(name)) watched on the
way: a style piece called "Classic" moving into a look slot that already has a "Classic" gets a
number, as the API gives one. Nothing is deleted, and no persona is touched, because the whole
chapter rests on a persona holding a copy of its text. The downgrade widens the constraint again
and leaves the moved rows where they are: a migration cannot split a three-paragraph piece back
into three, so it does not pretend to.

::: dotnet
An EF Core migration with `migrationBuilder.Sql(...)` in `Up()`, run before the
`AlterColumn`/check-constraint change — a *data* migration, which EF scaffolds nothing for.
`op.get_bind()` is the migration's open connection, the way `Database.GetDbConnection()` would be
inside `Up()`. Enums stored as text, as here, are what make this a row update and not a type
change; a Postgres `ENUM` type would have needed `ALTER TYPE … RENAME VALUE` and a type of its own.
:::

The extractor learned one rule — in the look and the personality, paragraphs that follow each
other are one piece — and was run again against the owner's personas, with the same proof as the
first time: a persona is saved as pieces only when they rejoin to its text exactly. The six real
personas did, from one look piece and one personality piece each, which was the point of the
exercise: the pool is right when every persona the owner wrote can be built back from it, and a
new one from the same pieces.

One more thing the second run made visible. A piece reads `{name} is an athletic young man …`
and, further down, `{short} descends from Clan Donald …` next to `He dresses …`. That is not a
muddle: `{name}` stands exactly where the persona wrote the full name (once, in the opening
sentence), `{short}` where it wrote the short name on its own, and a pronoun stays a pronoun. The
placeholders are what let the same piece serve another name, and the proof depends on them being
placed where the name was, not where a reader might prefer it.
