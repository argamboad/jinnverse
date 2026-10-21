# Renaming an application

On 2026-10-21 the owner brought two files to the `brand/` folder: the same robot genie rising
from the same lamp, the same navy, cream and gold, and a new word under it. Lustjinn was now
**JinnVerse**. A rename sounds like a search-and-replace, and most of it is one; the chapter is
about the parts that are not, because each of them lives somewhere a text editor cannot reach:
an installed environment, a database, a reader's device, and the accounts outside the
repository. Step 21, eight issues, one pull request, one commit each.

## Renaming a package

In C#, a project's name is written in three places that can disagree: the `.csproj` file name,
`AssemblyName` and `RootNamespace`. *Rename symbol* on a namespace walks every `using` for you,
and the build finds whatever it missed. Python has fewer places and no compiler, so the places
have to be known.

The package is a directory. `src/lustjinn/` became `src/jinnverse/` with `git mv`, which keeps
the history of every file across the move. The project is named once, in `pyproject.toml`
(`name = "jinnverse"`), and that name is what `uv` installs into the environment and what
`uv.lock` records; so the lock file changed with it, and `uv sync` had to run before anything
could import again. An environment that still held `lustjinn` would have imported the old copy
happily — the `src/` layout exists exactly so that nothing imports by accident (chapter 1), and
it cuts both ways.

The imports were a replace: `from lustjinn.` is `from jinnverse.` in 97 files. Two kinds of
reference hide from that replace because they are strings, not imports:

- `importlib.resources.files("lustjinn")`, which reads the data files packaged beside the code
  (`emoji.json`, `dials.json`, `status_fields.json`). In .NET those are embedded resources, and
  `Assembly.GetManifestResourceStream` names them by the assembly's name just the same.
- The terminal client's `files("lustjinn_tui").joinpath("words.txt")`, and one test that reached
  the API's emoji table by path, `src/lustjinn/emoji.json`. The test suite found that one: 693
  tests passed and one errored, which is the point of running all of them.

::: dotnet
`known-first-party` in ruff's isort settings is the one place the tooling needs the name: it is
how ruff tells "our" imports from third-party ones when it orders them, what the `.editorconfig`
`dotnet_sort_system_directives_first` and a `using` group do by convention in C#.
:::

The terminal client is a second package in the uv workspace, with a console script. Its three
names moved together: the directory `tui/src/jinnverse_tui/`, the project `jinnverse-tui`, and
the entry point `jinnverse-tui = "jinnverse_tui.app:main"`. `version.py` asks the installed
metadata for `jinnverse-tui`; asked for the old name it would have answered `dev`, the fallback
for a checkout that is not installed, and the masthead would have shown it. The class the screens
look for is `JinnverseApp`, and the property every screen reaches the app through, `self.lustjinn`
in chapter 9, is `self.jinnverse`.

## A prefix is a contract with the environment

The settings are read from variables named `LUSTJINN_<FIELD>` — one line in `settings.py`,
`env_prefix="LUSTJINN_"` (chapter 2), the pydantic-settings equivalent of the section name in
`Configuration.GetSection("Lustjinn").Bind(options)`. Changing it to `JINNVERSE_` is one line in
the code and a contract broken everywhere the code runs: `.env` on the laptop, `.env.staging`,
CI's job, and the environment Render holds for the staging service.

The order matters, and it is the opposite of the usual *deploy, then configure*. The renamed
code reads only the new prefix. Deployed before the variables are renamed, the service starts
with no database, no credentials and no model key — pydantic refuses to build `Settings`, so the
app refuses to start, which is the behaviour chapter 2 asked for. So the owner renames the
variables on Render first, then migrates Neon, then deploys (#252). The laptop's own `.env` files
are gitignored and the owner's, so the commit message says what to rename in them.

::: warning
A settings prefix, a connection-string key, a section name: anything a running environment
supplies by name is part of the deployable's interface. Rename it with the same care as an API
route, and write down the order of the two sides.
:::

## A name that lives in the database

Chapter 2 built the append-only trigger: `messages_append_only()`, a PL/pgSQL function that
refuses `UPDATE` of a turn's text and `DELETE` of a turn, with one door — a transaction that has
set `lustjinn.purging = 'on'` may delete, which is how a story is erased for good. The setting's
name is the app's name, and it is in the function's source, and the function's source is a row in
`pg_proc` on every database that ran migration 0002: the throwaway one each test run creates, the
local Postgres, Neon.

So the rename is a migration, 0021, the same way an EF Core migration carries a trigger: SQL
written by hand, because the models cannot describe a function.

```python
def function(setting: str) -> str:
    return f"""
        CREATE OR REPLACE FUNCTION messages_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF current_setting('{setting}', true) = 'on' THEN
                    RETURN OLD;
                END IF;
                ...
        """

def upgrade() -> None:
    op.execute(function("jinnverse.purging"))

def downgrade() -> None:
    op.execute(function("lustjinn.purging"))
```

`CREATE OR REPLACE` keeps the trigger that calls the function, so nothing else changes. The body
is the one from 0002 with the setting as a parameter, so upgrade and downgrade cannot drift
apart; the downgrade restores the old name, as every migration here can be undone (chapter 2's
`test_the_migrations_can_be_undone_and_applied_again` walks 0021 down and up like the rest).
`purge.py` sets the new name with `set_config('jinnverse.purging', 'on', true)` in the same
commit, because a setting the function reads and a setting the code sets are one contract too.

::: dotnet
`ALTER FUNCTION ... RENAME` exists, but it renames the function, not what the body reads.
There is no `Rename symbol` for a string inside stored SQL — in SQL Server you would `ALTER
TRIGGER` with the full new body for the same reason.
:::

The local Postgres took the new name too: `docker compose` project, user, password, database and
volume. A renamed volume is a new, empty volume; the old stories sit in `lustjinn-db` until
copied or dropped. Neon's database is `neondb` and never carried the app's name, which is the
better habit.

## State on the reader's device survives only on purpose

Both clients keep things on the device. The web app keeps the bearer token, the theme, the shelf
last open, the persona builder's pick and the "you have seen this hint" flag, each under a key
named `lustjinn-…` in `localStorage` or `sessionStorage`. The terminal client keeps `config.toml`
and the token in a directory named after the app, `%LOCALAPPDATA%\lustjinn` or
`~/.config/lustjinn`. Rename the keys and the directory, and the owner opens JinnVerse signed
out, navy again, with the defaults — the rename would have cost them exactly the state the
step's issues said to keep.

A one-time carry-over is the fix, and the design in both clients is the same three rules: move
the old entry to the new name; a value already under the new name wins; the old entry goes either
way, so the move cannot run twice.

The web app does it in `lib/storage.ts`, which owns the keys and runs the move as it loads — and
*as it loads* is the whole trick. The theme store reads its key when its module is evaluated,
and ES modules evaluate their dependencies first, so a module that every reader of a key imports
is guaranteed to run before any of them:

```ts
export function carryOver(storage: Storage): string[] {
	const moved: string[] = [];
	const former: string[] = [];
	for (let i = 0; i < storage.length; i++) {
		const key = storage.key(i);
		if (key?.startsWith(FORMER)) former.push(key);
	}
	for (const old of former) {
		const key = CURRENT + old.slice(FORMER.length);
		const value = storage.getItem(old);
		if (value !== null && storage.getItem(key) === null) storage.setItem(key, value);
		storage.removeItem(old);
		moved.push(key);
	}
	return moved;
}

try {
	if (typeof localStorage !== 'undefined') carryOver(localStorage);
	if (typeof sessionStorage !== 'undefined') carryOver(sessionStorage);
} catch {
	/* a private window: nothing to move */
}
```

One reader runs before any module: the inline script in `app.html` that applies the remembered
theme before the first paint, so a light-theme reader never sees a navy flash (chapter 8). It
cannot import, so it reads the new key and falls back to the old one — a one-line fallback, not a
second copy of the move. The test is a `Storage` over a `Map`, because vitest runs in Node,
where there is no `localStorage`.

The terminal client's version is `carry_over(new, old)` in `config.py`: when the new directory
does not exist and the old one does, `shutil.move` takes the directory whole, config and token,
on the first start. `main()` calls it before `write_default`, which would otherwise create the
new directory with the defaults and leave the old one stranded forever.

::: dotnet
A desktop app in .NET does this with `ApplicationSettingsBase.Upgrade()` after a version change,
or by hand with the previous `user.config`. The shape is the same: check for the new, read the
old, write once, never again.
:::

An installed PWA is the one thing that does not follow: a phone keeps the name and icon the app
was installed with, from the manifest it read that day. The owner removes and re-installs it to
see *JinnVerse* on the home screen.

## The name outside the repository

Three things carry the name and are not files in this repository.

**GitHub.** A repository rename redirects: clones, `gh`, links and the Render GitHub app keep
working through the old URL, and the local remotes get updated at leisure. So the rename happens
after the merge, and the code already points at `argamboad/jinnverse` (the `HTTP-Referer` sent to
OpenRouter, the docs) without a broken interval.

**Render.** A service's `onrender.com` URL is fixed when the service is created, and the
blueprint in `render.yaml` matches services by name. Renaming the services would mean recreating
them: new URLs, every environment variable set again, the deploy hook, the CORS list, the token
secret — or every device signed out. The owner chose to keep `lustjinn-staging` and
`lustjinn-web-staging` as they are (#252, decision 1); the old name survives in two hostnames,
which is a cheap place for it to survive.

**The laptop.** The checkout's folder, the workspace repository's list of repositories, a
Codespaces secret named after the folder, the memory directory keyed on the path. Those belong
to a different repository and a different session; the issue lists them and leaves them there.

## What the step cost

Eight commits, 975 tests green after the one the rename found, a migration that Neon applies in
under a second, and no screen changed — the design gate of chapter 8 never opened. The lesson is
the one the trigger taught: a name is not a word in the source; it is every place a running
system was told that word, and the rename is only done when each of those places has been found
and told again, in the right order.
