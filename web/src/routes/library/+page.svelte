<script lang="ts">
	import { onMount } from 'svelte';
	import AppBar from '#lib/AppBar.svelte';
	import LibraryRail from '#lib/LibraryRail.svelte';
	import Tabs from '#lib/Tabs.svelte';
	import { api, type Counts, type Defaults, type Entry, type Piece, type Shelf } from '#lib/api.ts';
	import { blurb, entryMeta, piecesSummary } from '#lib/library.ts';
	import { Media } from '#lib/media.svelte.ts';
	import { KEYS } from '#lib/storage.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	/** The three shelves. The persona pieces live under Personas, as a card that builds a persona
	 * and a link to their own list. */
	const shelves: { id: Shelf; label: string; one: string }[] = [
		{ id: 'characters', label: 'Characters', one: 'character' },
		{ id: 'personas', label: 'Personas', one: 'persona' },
		{ id: 'snippets', label: 'Snippets', one: 'snippet' }
	];

	let shelf = $state<Shelf>('characters');
	let hidden = $state(false);
	let entries = $state<Entry[] | null>(null);
	let pieces = $state<Piece[] | null>(null);
	let defaults = $state<Defaults | null>(null);
	let counts = $state<Counts | null>(null);

	const current = $derived(shelves.find((s) => s.id === shelf)!);
	/** From 900 px the library is a workspace: the rail, and an editor beside it once one is open. */
	const wide = new Media('(min-width: 900px)');
	const hiddenHere = $derived(counts?.hidden[shelf] ?? 0);

	onMount(() => {
		try {
			const saved = localStorage.getItem(KEYS.shelf);
			if (saved === 'personas' || saved === 'snippets') shelf = saved;
		} catch {
			/* a convenience only */
		}
		void load();
		void loadCounts();
		api
			.defaults()
			.then((d) => (defaults = d))
			.catch(() => undefined);
	});

	/** The tabs' numbers: all the shelves in one call; without them the tabs show no number. */
	async function loadCounts() {
		try {
			counts = await api.counts();
		} catch {
			/* a convenience only */
		}
	}

	async function load() {
		entries = null;
		try {
			entries = await api.entries(shelf, hidden);
			void loadCounts();
		} catch (error) {
			toasts.show(
				'danger',
				'Could not read the shelf',
				error instanceof Error ? error.message : undefined
			);
			entries = [];
		}
		if (shelf === 'personas' && pieces === null) {
			api
				.pieces()
				.then((found) => (pieces = found))
				.catch(() => (pieces = []));
		}
	}

	function pick(next: Shelf) {
		shelf = next;
		hidden = false;
		try {
			localStorage.setItem(KEYS.shelf, next);
		} catch {
			/* a convenience only */
		}
		void load();
	}

	function toggleHidden() {
		hidden = !hidden;
		void load();
	}

	function initial(entry: Entry): string {
		return entry.name.replace(/^_/, '').charAt(0).toUpperCase() || '?';
	}
</script>

{#if wide.current}
	<div class="libwide">
		<LibraryRail {shelf} />
		<div class="pick">
			<p class="muted">Pick an entry, or write a new one.</p>
		</div>
	</div>
{:else}
	<div class="screen">
		<AppBar title="Library" mark>
			{#snippet actions()}
				<a class="btn primary small" href="/library/{shelf}/new">+ New {current.one}</a>
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
		</div>
		<main class="list">
			{#if entries === null}
				<p class="muted center">Reading the shelf…</p>
			{:else if entries.length === 0 && !hidden}
				<div class="empty">
					<p class="muted">
						{#if shelf === 'snippets'}
							No snippets yet. A snippet is text you insert often — typed as <code>:name</code> in the
							composer, or picked from its list.
						{:else if shelf === 'personas'}
							No personas yet. A persona is who you are in a story; the default one plays in every
							story that names none.
						{:else}
							No characters yet. A character is a card — who they are, how they speak, where the
							scene opens.
						{/if}
					</p>
					<a class="btn primary" href="/library/{shelf}/new">Write the first {current.one}</a>
				</div>
			{:else}
				{#each entries as entry (entry.id)}
					{@const shown = blurb(entry)}
					{@const isDefault = shelf === 'personas' && defaults?.default_persona_id === entry.id}
					<a class="entry" href="/library/{shelf}/{entry.id}">
						<span class="who" class:gold={isDefault}>{initial(entry)}</span>
						<span class="text">
							<span class="name">
								{entry.name}
								{#if entry.hidden}<span class="chip">hidden</span>{/if}
								{#if isDefault}<span class="chip gold">default</span>{/if}
							</span>
							<span class="preview" class:prose={!shown.note}>{shown.text}</span>
							<span class="meta">{entryMeta(entry, shelf)}</span>
						</span>
						<span class="chev" aria-hidden="true">›</span>
					</a>
				{/each}
			{/if}

			{#if shelf === 'personas' && entries !== null}
				<div class="pieces">
					<h2>Pieces</h2>
					<a class="entry" href="/library/personas/from-pieces">
						<span class="who">P</span>
						<span class="text">
							<span class="name">Build a persona from pieces</span>
							<span class="summary">{pieces ? piecesSummary(pieces) : 'Reading the pieces…'}</span>
						</span>
						<span class="chev" aria-hidden="true">›</span>
					</a>
					<a class="browse" href="/library/pieces">Browse and edit the pieces ›</a>
				</div>
			{/if}

			{#if entries !== null && (hidden || hiddenHere > 0)}
				<button type="button" class="hidden-toggle" onclick={toggleHidden}>
					{#if hidden}
						Hide the <code>_name</code> entries
					{:else}
						Show {hiddenHere} hidden <code>_name</code>
						{hiddenHere === 1 ? 'entry' : 'entries'}
					{/if}
				</button>
			{/if}
		</main>
		<Tabs />
	</div>
{/if}

<style>
	.libwide {
		height: 100%;
		display: grid;
		grid-template-columns: 340px minmax(0, 1fr);
	}
	.pick {
		display: grid;
		place-items: center;
		padding: 24px;
	}
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
		padding: 10px 14px 6px;
	}
	.seg {
		display: flex;
		padding: 3px;
		gap: 2px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--line);
	}
	.seg button {
		flex: 1;
		white-space: nowrap;
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--fg-2);
		font-size: 0.85rem;
		font-weight: 500;
		padding: 6px 10px;
		min-height: 34px;
		border-radius: var(--r-pill);
	}
	.seg .n {
		margin-left: 5px;
		font-weight: 400;
		opacity: 0.7;
	}
	.seg button[aria-selected='true'] {
		background: var(--gold);
		color: var(--gold-ink);
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
	.who.gold {
		background: var(--gold-soft);
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
	.chev {
		color: var(--muted);
	}
	.pieces {
		margin-top: 10px;
		display: grid;
		gap: 8px;
	}
	.pieces h2 {
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
		font-weight: 600;
		padding: 0 4px;
	}
	.summary {
		color: var(--fg-2);
		font-size: 0.85rem;
	}
	.browse {
		justify-self: start;
		font-size: 0.85rem;
		font-weight: 600;
		text-decoration: none;
		color: var(--gold-text);
		padding: 4px 6px;
	}
	.hidden-toggle {
		appearance: none;
		margin-top: 6px;
		justify-self: start;
		border: 0;
		background: transparent;
		color: var(--muted);
		font-size: 0.8rem;
		padding: 6px 4px;
		min-height: 32px;
	}
</style>
