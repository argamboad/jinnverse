<script lang="ts">
	import { onMount, tick } from 'svelte';
	import AppBar from '#lib/AppBar.svelte';
	import Tabs from '#lib/Tabs.svelte';
	import {
		api,
		type Counts,
		type Defaults,
		type Entry,
		type Piece,
		type Shelf,
		type Slot
	} from '#lib/api.ts';
	import { blurb, hiddenCount, pieceBlurb } from '#lib/library.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	/** The three shelves of the library proper, and the pool of persona pieces beside them. */
	type LibraryShelf = Shelf | 'pieces';

	const shelves: { id: LibraryShelf; label: string; one: string }[] = [
		{ id: 'characters', label: 'Characters', one: 'character' },
		{ id: 'personas', label: 'Personas', one: 'persona' },
		{ id: 'snippets', label: 'Snippets', one: 'snippet' },
		{ id: 'pieces', label: 'Pieces', one: 'piece' }
	];

	let shelf = $state<LibraryShelf>('characters');
	let hidden = $state(false);
	let entries = $state<Entry[] | null>(null);
	let pieces = $state<Piece[] | null>(null);
	let slots = $state<Slot[]>([]);
	let defaults = $state<Defaults | null>(null);
	let counts = $state<Counts | null>(null);

	const current = $derived(shelves.find((s) => s.id === shelf)!);
	const hiddenHere = $derived(shelf === 'pieces' ? 0 : (counts?.hidden[shelf] ?? 0));
	/** The pool by slot, in the persona's own order; an empty slot is shown, so the gaps are seen. */
	const groups = $derived(
		slots.map((slot) => ({ slot, items: (pieces ?? []).filter((p) => p.slot === slot.key) }))
	);

	onMount(() => {
		try {
			const saved = localStorage.getItem('lustjinn-shelf');
			if (saved === 'personas' || saved === 'snippets' || saved === 'pieces') shelf = saved;
		} catch {
			/* a convenience only */
		}
		void load();
		void loadCounts();
		void showSelectedTab();
		api
			.defaults()
			.then((d) => (defaults = d))
			.catch(() => undefined);
	});

	/** The tabs' numbers: all the shelves in one call; without them the tabs show no number. */
	async function loadCounts() {
		try {
			counts = await api.counts();
			void showSelectedTab(); // the numbers widen the tabs
		} catch {
			/* a convenience only */
		}
	}

	async function load() {
		entries = null;
		pieces = null;
		try {
			if (shelf === 'pieces') {
				[slots, pieces] = await Promise.all([api.pieceSlots(), api.pieces()]);
			} else {
				entries = await api.entries(shelf, hidden);
			}
			void loadCounts();
		} catch (error) {
			toasts.show(
				'danger',
				'Could not read the shelf',
				error instanceof Error ? error.message : undefined
			);
			entries = [];
			pieces = [];
		}
	}

	/** On a narrow phone the tab strip scrolls sideways: the shelf in use is brought into view. */
	async function showSelectedTab() {
		await tick();
		document
			.querySelector('.seg [aria-selected="true"]')
			?.scrollIntoView({ inline: 'center', block: 'nearest' });
	}

	function pick(next: LibraryShelf) {
		shelf = next;
		void showSelectedTab();
		try {
			localStorage.setItem('lustjinn-shelf', next);
		} catch {
			/* a convenience only */
		}
		void load();
	}

	async function makeDefault(entry: Entry) {
		try {
			defaults = await api.setDefaults(entry.id);
			toasts.show(
				'ok',
				`${entry.name} is the default persona`,
				'Every story that names none plays as them.'
			);
		} catch (error) {
			toasts.show('danger', 'Not set', error instanceof Error ? error.message : undefined);
		}
	}

	function initial(entry: Entry): string {
		return entry.name.replace(/^_/, '').charAt(0).toUpperCase() || '?';
	}
</script>

<div class="screen">
	<AppBar title="Library" mark>
		{#snippet actions()}
			<a class="btn primary small" href="/library/{shelf}/new">New {current.one}</a>
		{/snippet}
	</AppBar>
	<div class="toolbar">
		<div class="seg" role="tablist" aria-label="Shelf">
			{#each shelves as s (s.id)}
				<button type="button" role="tab" aria-selected={shelf === s.id} onclick={() => pick(s.id)}
					>{s.label}{#if counts}<span class="n">{counts[s.id]}</span>{/if}</button
				>
			{/each}
		</div>
		{#if shelf !== 'pieces'}
			<label
				class="hidden-toggle"
				title="Entries whose name starts with _ (a template, working notes) are kept but not listed"
			>
				<input type="checkbox" bind:checked={hidden} onchange={load} />
				<span>Show hidden <code>_name</code>{hiddenCount(hiddenHere)}</span>
			</label>
		{/if}
		{#if shelf === 'personas'}
			<a class="btn ghost small build" href="/library/personas/from-pieces">Build from pieces</a>
		{/if}
	</div>
	<main class="list">
		{#if shelf === 'pieces'}
			{#if pieces === null}
				<p class="muted center">Reading the shelf…</p>
			{:else if pieces.length === 0}
				<div class="empty">
					<p class="muted">
						No pieces yet. A piece is one paragraph of a persona — a look, a home, a pet — and a
						persona is built by picking one for each.
					</p>
					<a class="btn primary" href="/library/pieces/new">Write the first piece</a>
				</div>
			{:else}
				{#each groups as group (group.slot.key)}
					<div class="slot">
						<h2>{group.slot.label} <span>{group.items.length}</span></h2>
						{#each group.items as piece (piece.id)}
							{@const shown = pieceBlurb(piece)}
							<a class="row" href="/library/pieces/{piece.id}">
								<span class="text">
									<span class="name">{piece.name}</span>
									<span class="preview" class:prose={!shown.note}>{shown.text}</span>
								</span>
								<span class="voice">{piece.voice}</span>
							</a>
						{/each}
					</div>
				{/each}
			{/if}
		{:else if entries === null}
			<p class="muted center">Reading the shelf…</p>
		{:else if entries.length === 0}
			<div class="empty">
				<p class="muted">
					{#if shelf === 'snippets'}
						No snippets yet. A snippet is text you insert often — typed as <code>:name</code> in the composer,
						or picked from its list.
					{:else if shelf === 'personas'}
						No personas yet. A persona is who you are in a story; the default one plays in every
						story that names none.
					{:else}
						No characters yet. A character is a card — who they are, how they speak, where the scene
						opens.
					{/if}
				</p>
				<a class="btn primary" href="/library/{shelf}/new">Write the first {current.one}</a>
			</div>
		{:else}
			{#each entries as entry (entry.id)}
				{@const shown = blurb(entry)}
				<a class="entry" href="/library/{shelf}/{entry.id}">
					<span class="who">{initial(entry)}</span>
					<span class="text">
						<span class="name">
							{entry.name}
							{#if entry.hidden}<span class="chip">hidden</span>{/if}
							{#if shelf === 'personas' && defaults?.default_persona_id === entry.id}
								<span class="chip gold">default</span>
							{/if}
						</span>
						<span class="preview" class:prose={!shown.note}>{shown.text}</span>
						<span class="meta"
							>v{entry.version} · {new Date(entry.updated_at).toLocaleDateString()}</span
						>
					</span>
					{#if shelf === 'personas' && defaults?.default_persona_id !== entry.id}
						<button
							type="button"
							class="link"
							onclick={(e) => {
								e.preventDefault();
								makeDefault(entry);
							}}>Make default</button
						>
					{/if}
				</a>
			{/each}
		{/if}
	</main>
	<Tabs />
</div>

<style>
	.screen {
		height: 100%;
		display: flex;
		flex-direction: column;
	}
	.btn.small {
		min-height: 36px;
		padding: 6px 14px;
		font-size: 0.85rem;
		text-decoration: none;
		white-space: nowrap;
		box-shadow: none;
	}
	.toolbar {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
		align-items: center;
		justify-content: space-between;
		padding: 10px 14px 6px;
	}
	.seg {
		display: inline-flex;
		max-width: 100%;
		overflow-x: auto;
		padding: 3px;
		gap: 2px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--line);
	}
	.seg button {
		white-space: nowrap;
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--fg-2);
		font-size: 0.85rem;
		font-weight: 500;
		padding: 6px 12px;
		min-height: 34px;
		border-radius: var(--r-pill);
	}
	.seg .n {
		margin-left: 6px;
		font-weight: 400;
		opacity: 0.7;
	}
	.seg button[aria-selected='true'] {
		background: var(--gold);
		color: var(--gold-ink);
	}
	.hidden-toggle {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 0.82rem;
		color: var(--muted);
	}
	.hidden-toggle input {
		accent-color: var(--gold);
		width: 18px;
		height: 18px;
	}
	.list {
		flex: 1;
		min-height: 0;
		overflow: auto;
		padding: 4px 12px 24px;
		display: grid;
		gap: 8px;
		align-content: start;
	}
	.center {
		text-align: center;
		padding: 32px 0;
	}
	.empty {
		display: grid;
		gap: 14px;
		justify-items: center;
		padding: 40px 16px;
		text-align: center;
	}
	.empty p {
		max-width: 46ch;
	}
	.entry {
		display: grid;
		grid-template-columns: 44px 1fr auto;
		gap: 12px;
		align-items: center;
		padding: 12px;
		border-radius: var(--r-m);
		background: var(--surface);
		border: 1px solid var(--line);
		text-decoration: none;
		color: inherit;
	}
	.who {
		width: 44px;
		height: 44px;
		border-radius: 12px;
		background: var(--surface-2);
		display: grid;
		place-items: center;
		font-family: var(--font-prose);
		font-size: 1.25rem;
		color: var(--gold-text);
	}
	.text {
		min-width: 0;
		display: grid;
		gap: 2px;
	}
	.name {
		font-weight: 600;
		display: flex;
		gap: 8px;
		align-items: center;
		flex-wrap: wrap;
	}
	.preview {
		color: var(--fg-2);
		font-size: 0.88rem;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.meta {
		font-size: 0.72rem;
		color: var(--muted);
	}
	.link {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--gold-text);
		font-weight: 600;
		font-size: 0.78rem;
		padding: 8px;
		min-height: 36px;
	}
	.slot {
		display: grid;
		gap: 6px;
		margin-top: 6px;
	}
	.slot h2 {
		display: flex;
		justify-content: space-between;
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--gold-text);
		padding: 0 4px;
	}
	.slot h2 span {
		color: var(--muted);
		letter-spacing: 0;
	}
	.row {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		padding: 10px 12px;
		border-radius: var(--r-s);
		background: var(--surface);
		border: 1px solid var(--line);
		text-decoration: none;
		color: inherit;
	}
	.row .name {
		font-weight: 500;
	}
	.voice {
		font-size: 0.72rem;
		color: var(--muted);
		white-space: nowrap;
	}
</style>
