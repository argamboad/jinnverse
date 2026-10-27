# Taking a feature out

Chapter 10 built a pool of persona pieces, a joiner, an extractor that proved every real persona
rebuilt from the pool exactly, and a picker in each client; chapter 10's closing section folded
its twelve slots into eight. On 2026-10-27 the owner, who had been curating that pool, decided it
goes: the feature did not work as expected and confused the user, and the one-line description
each library entry had carried since #160 was doing the job the builder was meant to do —
telling personas apart and making a new one quick to start. Step 23 took it out: three code
issues, one per codebase, a docs issue, this chapter, and one issue for the owner after the
merge. The feature is the smaller lesson. The larger one is that **removing a feature is a
step like any other**, with tests, a migration, a review of every edge, and a cost line — not a
`git revert`.

## Why not a revert

The pull request that built the pieces (#159) is still in the history, and `git revert -m 1`
of a merge commit is one command. It would not have worked, for two reasons that hold for any
feature older than a sprint.

**The data outlived the code.** A revert of #159 reverts migration 0016 out of the repository,
but Neon has run 0016, 0017 and 0022 and holds 56 rows in `persona_pieces`. A database that is
ahead of its migration folder is exactly what Alembic cannot describe — `alembic current` would
name a revision no file knows — and chapter 2's rule was that the models and the migrations
agree on every database the app has touched. The table has to be dropped *forward*, by a new
migration, whatever happens to the code.

**The code drifted since.** Every step after #159 touched the feature. The descriptions and
counts (#166) gave pieces a description and a count on the shelves; the terminal client's
library parity (chapter 16) rebuilt its pieces shelf and its `N` flow around slots; the rename
(chapter 18) renamed the builder's storage key and its screen class; the eight slots (chapter
10's closing section) rewrote the enum, the extractor and both pickers. A revert of #159 would
conflict in most of those files, and a revert of the chain would take the descriptions and the
rename with it. The feature was not a commit any more; it was a set of edges spread through
three codebases, and the only honest way to remove edges is to find each one.

::: dotnet
The same choice exists in a .NET repository and resolves the same way. `Remove-Migration`
takes back only the *last* migration, and refuses one the database has already applied; a
table a production database holds is dropped by a new migration, never by deleting the old one. And a revert of a
merged PR in a solution where later PRs touched the same `.cs` files produces the same conflict
list `git` would produce here — the language does not change the arithmetic.
:::

## The migration: a drop, and a downgrade that must recreate

Migration 0023 is the shortest in the folder and carries the most consequence:

```python
def upgrade() -> None:
    op.drop_index("uq_persona_pieces_slot_voice_name_lower", table_name="persona_pieces")
    op.drop_table("persona_pieces")
```

Two lines, and 56 rows the owner curated by hand are gone the moment Neon runs them. The
decision was the owner's, made before the migration was written and recorded in its docstring
and in the issue for the deploy (#263): no export, the rows go. The chapter 7 precedent checked
the data first and found nothing to lose; this time there was something, and the owner chose to
lose it. The migration does not decide that; it records that it was decided.

The downgrade is where the work is:

```python
def downgrade() -> None:
    op.create_table(
        "persona_pieces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("slot", sa.String(length=20), nullable=False),
        sa.Column("voice", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("short", sa.String(length=100), nullable=True),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.CheckConstraint(f"slot IN {SLOTS}", name="ck_persona_pieces_slot"),
        sa.CheckConstraint("voice IN ('he', 'she', 'they', 'any')",
                           name="ck_persona_pieces_voice"),
        sa.CheckConstraint("(slot = 'name') = (short IS NOT NULL)",
                           name="ck_persona_pieces_short_only_for_names"),
        sa.PrimaryKeyConstraint("id", name="pk_persona_pieces"),
    )
    op.create_index("uq_persona_pieces_slot_voice_name_lower", "persona_pieces",
                    ["slot", "voice", sa.literal_column("lower(name)")], unique=True)
```

That is the table *as 0022 left it*: 0016's columns, 0017's `description`, 0022's narrowed
`SLOTS` constraint, under the names the earlier migrations gave them. The names are not
decoration. Chapter 2's `test_the_migrations_can_be_undone_and_applied_again` walks the whole
chain to `base` and back to `head` on a throwaway database, and on the way down 0022's own
downgrade runs `op.drop_constraint("ck_persona_pieces_slot", ...)` and 0016's runs
`op.drop_index("uq_persona_pieces_slot_voice_name_lower", ...)`. A downgrade that recreated the
table with a different constraint name would pass its own step and fail the one below it. So
the downgrade is copied from the migrations it undoes, read and tidied by hand, as `CLAUDE.md`
asks of every autogenerated draft.

What the downgrade cannot do is bring the rows back; it recreates the table empty. Chapter 7
said the same of a dropped column. The difference in degree is the point of writing it down: a
column's values and a table's rows are both lost by `upgrade`, and a downgrade is a promise
about the *shape* of the schema, never about its contents.

::: dotnet
`op.drop_table` is `migrationBuilder.DropTable` in `Up()`; `op.create_table` in `downgrade` is
the `CreateTable` EF scaffolds into `Down()` from its model snapshot. EF gets the names right for
free because the snapshot remembers them; Alembic keeps no snapshot (chapter 2), so a dropped
table's downgrade is written against the migrations that built it, and the undo-and-redo test
is what stands in for the snapshot. Either way, `Down()` with a `CreateTable` is a schema
promise only — nobody expects an EF `Down()` to restore rows, and nobody should expect it here.
:::

The schema test from chapter 2 — `test_the_migrations_build_exactly_what_the_models_describe`,
`compare_metadata` against a database at `head` — is the other half of the contract. Delete
`PersonaPiece` from `models.py` without 0023 and it fails, because the database has a table the
models do not describe; write 0023 without deleting the model and it fails the other way. The
model and the migration went in the same commit, which is the only way that test stays green
between two commits.

## Finding every edge

A feature that has been in an app for thirteen steps is not in one place. The way to find its
edges is to delete the obvious centre and let the tooling complain, then read for what the
tooling cannot see.

**The API.** `persona_pieces.py` (the router, the joiner, the slot list) and
`persona_extract.py` are deleted, with their tests and the extraction script. `PersonaPiece`,
`PieceSlot` and `Voice` leave `models.py`; `main.py` loses one `include_router` line. Pyright in
strict mode then finds every import of a name that no longer exists, the way a C# build would —
the first gate, and the cheapest. What it does not find is an edge that *compiles*: `Counts`
in `library.py` had a `pieces: int` field and a `select(func.count()).select_from(PersonaPiece)`
behind it. Pyright caught the import; the field's test caught the shape:

```python
    counts = (await client.get("/library/counts")).json()

    assert counts == {
        "characters": 2,
        "personas": 1,
        "snippets": 1,
        "hidden": {"characters": 0, "personas": 0, "snippets": 0},
    }
```

A test that asserts the whole body, not one key of it, is the test that notices a key leaving.
That is why the counts tests were written that way in #160, and why this step changed the
expected body rather than loosening the assertion.

**The web client.** Three routes (`library/pieces`, `library/pieces/[id]`,
`library/personas/from-pieces`) and `lib/personaBuilder.ts` with its spec are deleted. The
API client loses `Voice`, `Slot`, `Piece`, `PersonaPreview`, `BuiltPersona`, the calls that
used them and the `pieces` count on `Counts`; `lib/library.ts` loses `pieceBlurb` and
`piecesSummary`. svelte-check is the type checker here, and it finds each component that still
imported one of those names. What a type checker cannot find is a *link*: an `<a href>` is a
string. Those were found by reading — the "Build a persona from pieces" card on the Personas
shelf, two links in the library rail, the dashed "Build a new persona from pieces" row on the
new-story page, and the styles that dressed each one. A dead link in a static site is not an
error at build time; it is a 404 the owner finds on the phone.

**The terminal client.** `builder.py` is 633 lines and the easiest part: delete it, and
pyright names every screen that pushed it. The edges were elsewhere. The library screen had a
fourth shelf, a `PieceEntry` type, a `voice` key, a `short`-name mode, a `B` binding and a
palette command; the new-story screen had `Ctrl+B`; the help screen had a *Persona builder*
section and piece rows in the *Library* one; the skeletons had a piece template; the fake
server the tests run against had a pool of pieces. Each of those is a place a key or a word
appears, and the test that keeps them honest is the drift test from chapter 16:

```python
def test_every_key_in_the_legend_is_in_help(hints: tuple[Hint, ...], section: str) -> None:
    missing = {k for hint in hints for k in keys(hint.key)} - in_help(section)
    assert not missing, f"{section}: the legend names {sorted(missing)} and help does not"
```

It caught one. The help screen's *Library* section lost its `B` row, and the library screen's
legend still carried `Hint("B", "Build persona")`: the test failed naming `['B']`, and the
stale hint went. A legend that offers a key that
does nothing is the kind of edge no type checker sees and every reader does.

::: dotnet
The three gates line up with what a .NET developer leans on: pyright and svelte-check are the
compiler, finding every reference to a removed symbol; the whole-body test and the drift test
are the xUnit tests that assert a *contract* (the shape of a response, "every key in the legend
has a help entry") rather than a value, and so fail when a contract shrinks. The links are the
part neither catches — in Razor they would be `asp-page` tag helpers that throw when the view
renders and the page is gone, and that is a real advantage of a server that knows its routes
over a static site that does not.
:::

::: warning
Delete the centre first and read the failures; then read for strings. Routes, keys, help text,
skeleton templates and test fakes are all strings, and a feature's last traces are always in
strings.
:::

## What "did not work as expected" teaches

The pieces were built well. The joiner was a pure function with a proof by round trip; the slot
list was a closed vocabulary the database enforced; every real persona rebuilt from the pool
exactly, twice. None of that is why it went. It went because the owner, using it, found a second
vocabulary to curate — 56 pieces, leftovers from the first extraction sitting beside the merged
ones, twelve slots that were "overdone" and then eight, placeholders that read as scrambled even
though the exact rebuild depended on them — where the need had been a quick way to tell
personas apart and start a new one. A description on the entry, one line and no new table, met
that need.

The lesson is not that the feature was badly built; it is that correctness was measured against
the wrong thing. The measure the owner gave in Step 22 — *every real persona rebuilds exactly* —
is a property of the data, and the pool passed it. The property that mattered was whether the
owner reached for the builder, and nothing in the tests could say. A feature can be proven and
still be wrong, and the proof can hide it: the better the round trip, the longer it takes to ask
whether the trip was wanted.

Two things made the removal cheap, and both were decided in chapter 10 before a line of the
feature existed. The persona stayed plain text, and a built persona held a *copy* of its pieces,
never a reference. So no persona, no story, no prompt, no search and no export knew the pieces
existed, and the deletion stopped at the feature's own edges. The decision "what not to build"
is also the decision "what will not have to be unbuilt".

::: note
Chapter 7's model per story went the same way: built, measured, and found to change nothing a
reader could name. Two features taken out in nineteen chapters is not a failure rate; it is the
cost of finding out, paid in the currency that is cheapest here — code that was written to be
deleted cleanly.
:::

## What the step cost

Three code commits, one per codebase, in one pull request with the docs and this chapter.
Across the three: 33 files, 95 lines added, 5,778 removed. The tests went with the code they
tested — 55 API tests, 44 terminal tests and 20 web spec cases — and every
remaining gate stayed green: pytest, ruff, pyright, prettier, svelte-check, vitest and the web
build. No screen was designed, so the gate of chapter 8 never opened. The migration runs in
under a second on Neon and is the one part that cannot be undone, which is why #263 asks the
owner to run it before the deploy: the old code counts pieces on every library screen and would
fail the moment the table is gone, and the new code never asks.

The course keeps chapter 10 with a note at its head, as it kept the model per story inside
chapter 7. What a step taught does not go when the feature does; the record of a removed feature
is how the next one avoids being built to the wrong measure.
