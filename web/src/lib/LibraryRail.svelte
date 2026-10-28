<script lang="ts">
	import { onMount, untrack } from 'svelte';
	import { api, type Counts, type Defaults, type Entry, type Shelf } from '#lib/api.ts';
	import { blurb, entryMeta } from '#lib/library.ts';
	import RailHead from '#lib/RailHead.svelte';
	import { KEYS } from '#lib/storage.ts';

	/** The wide library's left rail: the shelves as tabs, the entries of the one shown (the open
	 * one marked), the hidden `_name` ones on request, and the way to write another. The shelf it
	 * shows follows the entry that is open, and can be switched without leaving it. */
	let {
		shelf,
		current,
		stamp = ''
	}: {
		shelf: Shelf;
		current?: string;
		/** Changes when the open entry is saved, so the list shows its new name and version. */
		stamp?: string;
	} = $props();

	const shelves: { id: Shelf; label: string; one: string }[] = [
		{ id: 'characters', label: 'Characters', one: 'character' },
		{ id: 'personas', label: 'Personas', one: 'persona' },
		{ id: 'snippets', label: 'Snippets', one: 'snippet' }
	];

	let shown = $state<Shelf>(untrack(() => shelf));
	let hidden = $state(false);
	let entries = $state<Entry[] | null>(null);
	let counts = $state<Counts | null>(null);
	let defaults = $state<Defaults | null>(null);

	const one = $derived(shelves.find((s) => s.id === shown)!.one);
	const hiddenHere = $derived(counts?.hidden[shown] ?? 0);

	// Opening an entry of another shelf brings its shelf into the rail.
	$effect(() => {
		const next = shelf;
		untrack(() => {
			if (next !== shown) pick(next);
		});
	});

	// The list, whenever the shelf or the hidden switch changes.
	$effect(() => {
		const target = shown;
		const withHidden = hidden;
		void stamp;
		api
			.entries(target, withHidden)
			.then((found) => {
				if (target === shown) entries = found;
			})
			.catch(() => (entries = []));
	});

	onMount(() => {
		api
			.counts()
			.then((c) => (counts = c))
			.catch(() => undefined);
		api
			.defaults()
			.then((d) => (defaults = d))
			.catch(() => undefined);
	});

	function pick(next: Shelf) {
		if (next !== shown) entries = null;
		shown = next;
		hidden = false;
		try {
			localStorage.setItem(KEYS.shelf, next);
		} catch {
			/* a convenience only */
		}
	}

	function initial(entry: Entry): string {
		return entry.name.replace(/^_/, '').charAt(0).toUpperCase() || '?';
	}
</script>

<aside class="rail" aria-label="Library">
	<RailHead section="library" />
	<div class="tabs" role="tablist" aria-label="Shelf">
		{#each shelves as s (s.id)}
			<button type="button" role="tab" aria-selected={shown === s.id} onclick={() => pick(s.id)}
				>{s.label}{#if counts}<span class="n">{counts[s.id]}</span>{/if}</button
			>
		{/each}
	</div>
	<div class="list">
		{#if entries === null}
			<p class="muted small">Reading the shelf…</p>
		{:else if entries.length === 0 && !hidden}
			<p class="muted small">Nothing on this shelf yet.</p>
		{:else}
			{#each entries as entry (entry.id)}
				{@const note = blurb(entry)}
				<a
					class="row"
					class:on={entry.id === current}
					aria-current={entry.id === current ? 'page' : undefined}
					href="/library/{shown}/{entry.id}"
				>
					<span
						class="tile"
						class:gold={entry.id === current ||
							(shown === 'personas' && defaults?.default_persona_id === entry.id)}
						>{initial(entry)}</span
					>
					<span class="text">
						<span class="name">{entry.name}</span>
						<span class="blurb" class:prose={!note.note}>{note.text}</span>
						<span class="meta">{entryMeta(entry, shown)}</span>
					</span>
				</a>
			{/each}
		{/if}
		{#if entries !== null && (hidden || hiddenHere > 0)}
			<button type="button" class="hidden-toggle" onclick={() => (hidden = !hidden)}>
				{#if hidden}
					Hide the <code>_name</code> entries
				{:else}
					Show {hiddenHere} hidden <code>_name</code>
					{hiddenHere === 1 ? 'entry' : 'entries'}
				{/if}
			</button>
		{/if}
	</div>
	<div class="foot">
		<a class="new btn primary" href="/library/{shown}/new">+ New {one}</a>
	</div>
</aside>

<style>
	.rail {
		display: flex;
		flex-direction: column;
		min-height: 0;
		min-width: 0;
		background: var(--bg-2);
		border-right: 1px solid var(--line);
	}
	.tabs {
		margin: 0 12px 8px;
		display: flex;
		padding: 3px;
		gap: 2px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--line);
	}
	.tabs button {
		flex: 1;
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--fg-2);
		font-size: 0.82rem;
		font-weight: 500;
		padding: 5px 8px;
		min-height: 32px;
		border-radius: var(--r-pill);
		white-space: nowrap;
	}
	.tabs button[aria-selected='true'] {
		background: var(--gold);
		color: var(--gold-ink);
	}
	.n {
		margin-left: 5px;
		font-weight: 400;
		opacity: 0.7;
	}
	.list {
		flex: 1;
		min-height: 0;
		overflow: auto;
		padding: 0 8px 12px;
		display: grid;
		gap: 4px;
		align-content: start;
	}
	.small {
		font-size: 0.82rem;
		padding: 8px 10px;
	}
	.row {
		display: grid;
		grid-template-columns: 36px 1fr;
		gap: 10px;
		padding: 10px;
		border-radius: 12px;
		border: 1px solid transparent;
		text-decoration: none;
		color: inherit;
	}
	.row:hover {
		background: var(--surface);
	}
	.row.on {
		background: var(--surface);
		border-color: var(--you-line);
	}
	.tile {
		width: 36px;
		height: 36px;
		border-radius: 10px;
		background: var(--surface-2);
		display: grid;
		place-items: center;
		font-family: var(--font-prose);
		font-size: 1.1rem;
		color: var(--gold-text);
	}
	.tile.gold {
		background: var(--gold-soft);
	}
	.text {
		min-width: 0;
		display: grid;
		gap: 1px;
	}
	.name {
		font-weight: 600;
		font-size: 0.92rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.blurb {
		color: var(--fg-2);
		font-size: 0.8rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.meta {
		font-size: 0.7rem;
		color: var(--muted);
	}
	.hidden-toggle {
		appearance: none;
		margin-top: 8px;
		justify-self: start;
		border: 0;
		background: transparent;
		color: var(--muted);
		font-size: 0.78rem;
		padding: 6px 10px;
	}
	.foot {
		padding: 10px 12px 12px;
		border-top: 1px solid var(--line);
	}
	.new {
		display: flex;
		width: 100%;
		min-height: 40px;
		font-size: 0.9rem;
		text-decoration: none;
	}
</style>
