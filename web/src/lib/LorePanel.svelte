<script lang="ts">
	import { api, ApiError, type LoreEntry } from '#lib/api.ts';
	import { keysLine, keysNote, parseKeys } from '#lib/library.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	/** A character's lorebook, under its card: the entries in the order they were made, each
	 * opening into a small editor of its own (name, keys on one line, text) that saves from its
	 * own buttons — a document saves when you say so — with the version check and the conflict
	 * notice the card has. One entry is edited at a time. */
	let {
		characterId,
		characterName,
		dirty = $bindable(false)
	}: { characterId: string; characterName: string; dirty?: boolean } = $props();

	let entries = $state<LoreEntry[] | null>(null);
	/** The entry open in the editor, or 'new' for one being added. */
	let editing = $state<string | null>(null);
	let name = $state('');
	let keys = $state('');
	let text = $state('');
	let version = $state(0);
	let busy = $state(false);
	let deleting = $state<string | null>(null);
	/** The entry as the server has it, when a save found it changed elsewhere. */
	let theirs = $state<LoreEntry | null>(null);

	const opened = $derived(entries?.find((e) => e.id === editing) ?? null);
	const changed = $derived(
		editing === 'new'
			? name.trim().length > 0 || keys.trim().length > 0 || text.trim().length > 0
			: opened !== null &&
					(name.trim() !== opened.name ||
						keysLine(parseKeys(keys)) !== keysLine(opened.keys) ||
						text !== opened.text)
	);
	const ready = $derived(
		name.trim().length > 0 && parseKeys(keys).length > 0 && text.trim().length > 0 && !busy
	);
	$effect(() => {
		dirty = editing !== null && changed;
	});

	let shownFor = '';
	$effect(() => {
		if (characterId !== shownFor) {
			shownFor = characterId;
			entries = null;
			close();
			void load();
		}
	});

	async function load() {
		try {
			entries = await api.lore(characterId);
		} catch (error) {
			entries = [];
			toasts.show(
				'danger',
				'Could not read the lore',
				error instanceof Error ? error.message : undefined
			);
		}
	}

	function open(entry: LoreEntry) {
		editing = entry.id;
		name = entry.name;
		keys = keysLine(entry.keys);
		text = entry.text;
		version = entry.version;
		theirs = null;
		deleting = null;
	}

	function add() {
		editing = 'new';
		name = keys = text = '';
		version = 0;
		theirs = null;
		deleting = null;
	}

	function close() {
		editing = null;
		name = keys = text = '';
		theirs = null;
		deleting = null;
	}

	async function save() {
		if (!ready || entries === null) return;
		busy = true;
		try {
			if (editing === 'new') {
				const made = await api.createLore(characterId, {
					name: name.trim(),
					keys: parseKeys(keys),
					text
				});
				entries = [...entries, made];
				toasts.show(
					'ok',
					`${made.name} is in the lore`,
					'Sent while one of its keys is in the scene.'
				);
				close();
			} else if (editing) {
				const saved = await api.saveLore(characterId, editing, {
					version,
					name: name.trim(),
					keys: parseKeys(keys),
					text
				});
				entries = entries.map((e) => (e.id === saved.id ? saved : e));
				toasts.show('ok', `Saved as v${saved.version}`);
				close();
			}
		} catch (error) {
			if (error instanceof ApiError && error.status === 409 && isConflict(error.body)) {
				theirs = error.body.current;
				version = theirs.version; // saving again replaces what is there now
			} else {
				toasts.show(
					'danger',
					'Not saved',
					error instanceof Error ? error.message : undefined,
					8000
				);
			}
		} finally {
			busy = false;
		}
	}

	function isConflict(body: unknown): body is { message: string; current: LoreEntry } {
		return typeof body === 'object' && body !== null && 'current' in body;
	}

	function takeTheirs() {
		if (theirs) open(theirs);
	}

	async function remove(entry: LoreEntry) {
		if (entries === null) return;
		busy = true;
		try {
			await api.deleteLore(characterId, entry.id);
			entries = entries.filter((e) => e.id !== entry.id);
			toasts.show('ok', `Deleted ${entry.name}`);
			if (editing === entry.id) close();
		} catch (error) {
			toasts.show('danger', 'Not deleted', error instanceof Error ? error.message : undefined);
		} finally {
			busy = false;
			deleting = null;
		}
	}
</script>

<section class="lore" aria-label="Lore">
	<div class="head">
		<h2>Lore</h2>
		<small class="muted">
			{#if entries === null}
				Reading…
			{:else if entries.length === 0}
				Nothing yet
			{:else}
				{entries.length}
				{entries.length === 1 ? 'entry' : 'entries'} · sent only while a key is in the scene
			{/if}
		</small>
		{#if editing === null}
			<button type="button" class="btn ghost tiny" onclick={add} disabled={entries === null}
				>Add an entry</button
			>
		{/if}
	</div>
	<p class="muted small">
		A piece of the card moved out of it — a character's sheet, a place, a timetable — with the words
		that bring it in. The card is sent whole every turn; an entry only while one of its keys was
		said in the last six turns or stands in the status block.
	</p>

	{#if editing !== null}
		<div class="editor">
			{#if theirs}
				<div class="conflict" role="alert">
					<b>This entry changed somewhere else since you opened it.</b>
					<p class="muted">Nothing was saved. Their text is below; yours is in the editor.</p>
					<pre class="prose">{theirs.text}</pre>
					<div class="row">
						<button type="button" class="btn primary tiny" onclick={save}
							>Replace it with mine</button
						>
						<button type="button" class="btn ghost tiny" onclick={takeTheirs}>Take theirs</button>
					</div>
				</div>
			{/if}
			<div class="pair">
				<label class="field">
					<span>Name <small class="muted">· a handle, never sent</small></span>
					<input class="input" type="text" bind:value={name} maxlength="200" placeholder="Jax" />
				</label>
				<label class="field">
					<span>Keys <small class="muted">· comma-separated; whole words, any case</small></span>
					<input
						class="input"
						type="text"
						bind:value={keys}
						placeholder="jax, bartender, the brewery"
					/>
				</label>
			</div>
			<label class="field">
				<span>The text</span>
				<textarea
					class="input prose doc"
					bind:value={text}
					rows="8"
					placeholder="What the model is told while this is in the scene…"></textarea>
			</label>
			<div class="row">
				<button type="button" class="btn primary" onclick={save} disabled={!ready || !changed}
					>{busy
						? 'Saving…'
						: editing === 'new'
							? 'Add the entry'
							: `Save as v${version + 1}`}</button
				>
				<button type="button" class="btn ghost" onclick={close} disabled={busy}>Cancel</button>
				<span class="muted small grow">
					{editing === 'new' ? `Goes with ${characterName}` : opened ? `v${opened.version}` : ''}
				</span>
			</div>
		</div>
	{/if}

	{#if entries !== null && entries.length > 0}
		<ul class="entries">
			{#each entries as entry (entry.id)}
				<li class="entry" class:open={editing === entry.id}>
					<button type="button" class="row-main" onclick={() => open(entry)} disabled={busy}>
						<span class="name">{entry.name}</span>
						<span class="keys">{keysNote(entry.keys)}</span>
						<span class="preview prose">{entry.text.slice(0, 160)}</span>
					</button>
					<div class="actions">
						{#if deleting === entry.id}
							<button
								type="button"
								class="btn danger tiny"
								onclick={() => remove(entry)}
								disabled={busy}>Delete</button
							>
							<button type="button" class="btn ghost tiny" onclick={() => (deleting = null)}
								>Keep</button
							>
						{:else}
							<button
								type="button"
								class="x"
								aria-label="Delete {entry.name}"
								title="Delete"
								onclick={() => (deleting = entry.id)}
								disabled={busy}>×</button
							>
						{/if}
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.lore {
		display: grid;
		gap: 10px;
		padding-top: 12px;
		border-top: 1px solid var(--line);
	}
	.head {
		display: flex;
		align-items: baseline;
		gap: 10px;
		flex-wrap: wrap;
	}
	.head h2 {
		font-size: 1rem;
	}
	.head small {
		flex: 1;
		font-size: 0.78rem;
	}
	.small {
		font-size: 0.82rem;
	}
	.grow {
		flex: 1;
		text-align: right;
	}
	.btn.tiny {
		min-height: 34px;
		padding: 4px 12px;
		font-size: 0.8rem;
	}
	.btn.danger {
		color: var(--danger);
	}
	.editor {
		display: grid;
		gap: 12px;
		padding: 12px;
		border-radius: var(--r-m);
		background: var(--surface);
		border: 1px solid var(--gold);
	}
	.pair {
		display: grid;
		gap: 12px;
	}
	@media (min-width: 1100px) {
		.pair {
			grid-template-columns: 1fr 1.4fr;
		}
	}
	textarea.doc {
		resize: vertical;
		line-height: 1.55;
		font-size: 1rem;
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		align-items: center;
	}
	.conflict {
		display: grid;
		gap: 10px;
		padding: 12px;
		border-radius: var(--r-s);
		border: 1px solid var(--warn);
		background: var(--surface-2);
	}
	.conflict pre {
		white-space: pre-wrap;
		margin: 0;
		max-height: 200px;
		overflow: auto;
		font-size: 0.9rem;
	}
	.entries {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 6px;
	}
	.entry {
		display: flex;
		align-items: stretch;
		gap: 6px;
		border-radius: var(--r-s);
		background: var(--surface);
		border: 1px solid var(--line);
	}
	.entry.open {
		border-color: var(--gold);
	}
	.row-main {
		appearance: none;
		flex: 1;
		min-width: 0;
		display: grid;
		gap: 2px;
		text-align: left;
		padding: 10px 12px;
		border: 0;
		background: transparent;
		color: var(--fg);
	}
	.name {
		font-weight: 600;
	}
	.keys {
		font-size: 0.76rem;
		color: var(--gold-text);
	}
	.preview {
		font-size: 0.84rem;
		color: var(--fg-2);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.actions {
		display: flex;
		align-items: center;
		gap: 6px;
		padding-right: 8px;
	}
	.x {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--muted);
		font-size: 1.1rem;
		min-width: 36px;
		min-height: 36px;
		border-radius: var(--r-pill);
	}
	.x:hover {
		color: var(--danger);
	}
</style>
