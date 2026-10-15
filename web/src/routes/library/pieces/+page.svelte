<script lang="ts">
	import { onMount } from 'svelte';
	import AppBar from '#lib/AppBar.svelte';
	import { api, type Piece, type Slot } from '#lib/api.ts';
	import { pieceBlurb, piecesSummary } from '#lib/library.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	/** The pool of persona pieces, by slot: what a persona is built from. Reached from the
	 * Personas shelf; a piece opens in its own editor. */
	let pieces = $state<Piece[] | null>(null);
	let slots = $state<Slot[]>([]);

	/** The pool by slot, in the persona's own order; an empty slot is shown, so the gaps are seen. */
	const groups = $derived(
		slots.map((slot) => ({ slot, items: (pieces ?? []).filter((p) => p.slot === slot.key) }))
	);

	onMount(async () => {
		try {
			[slots, pieces] = await Promise.all([api.pieceSlots(), api.pieces()]);
		} catch (error) {
			toasts.show(
				'danger',
				'Could not read the pieces',
				error instanceof Error ? error.message : undefined
			);
			pieces = [];
		}
	});
</script>

<div class="screen">
	<AppBar title="Pieces" sub={pieces?.length ? piecesSummary(pieces) : undefined} back="/library">
		{#snippet actions()}
			<a class="btn primary small" href="/library/pieces/new">+ New piece</a>
		{/snippet}
	</AppBar>
	<main class="list">
		{#if pieces === null}
			<p class="muted center">Reading the pieces…</p>
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
	</main>
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
	.list {
		flex: 1;
		min-height: 0;
		overflow: auto;
		padding: 8px 12px 24px;
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
	.text {
		min-width: 0;
		display: grid;
		gap: 2px;
	}
	.name {
		font-weight: 500;
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
	.voice {
		font-size: 0.72rem;
		color: var(--muted);
		white-space: nowrap;
	}
</style>
