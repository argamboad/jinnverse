<script lang="ts">
	import { onMount } from 'svelte';
	import AppBar from '#lib/AppBar.svelte';
	import StoriesRail from '#lib/StoriesRail.svelte';
	import StoryList from '#lib/StoryList.svelte';
	import Tabs from '#lib/Tabs.svelte';
	import { Media, WIDE } from '#lib/media.svelte.ts';
	import { stories } from '#lib/stories.svelte.ts';

	/** From 1100 px this is the story workspace with no story open: the rail, and an empty pane.
	 * Narrower windows keep the list as a screen of its own. */
	const wide = new Media(WIDE);

	let query = $state('');
	let pulling = $state(0); // pull-to-refresh distance

	// The month's spend lives on You now; this bar only counts.
	const sub = $derived.by(() => {
		const n = stories.list?.length;
		return n === undefined ? '' : n === 1 ? '1 story' : `${n} stories`;
	});

	onMount(() => {
		void stories.refresh();
	});

	// --- pull to refresh -------------------------------------------------------------------
	let pullStart: number | null = null;
	let scroller: HTMLElement | undefined = $state();

	function touchstart(event: TouchEvent) {
		if ((scroller?.scrollTop ?? 1) <= 0) pullStart = event.touches[0].clientY;
	}
	function touchmove(event: TouchEvent) {
		if (pullStart === null) return;
		pulling = Math.max(0, Math.min(90, (event.touches[0].clientY - pullStart) / 2));
	}
	async function touchend() {
		if (pulling > 60) await stories.refresh();
		pulling = 0;
		pullStart = null;
	}
</script>

{#if wide.current}
	<div class="workspace">
		<StoriesRail />
		<div class="pick">
			<p class="muted">Pick a story, or <a href="/new">start one</a>.</p>
		</div>
	</div>
{:else}
	<div class="screen">
		<AppBar title="Stories" {sub} mark>
			{#snippet actions()}
				<a class="avatar" href="/you" aria-label="You">R</a>
			{/snippet}
		</AppBar>
		<div class="search">
			<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"
				><path
					d="M10 2a8 8 0 1 0 4.9 14.3l5.4 5.4 1.4-1.4-5.4-5.4A8 8 0 0 0 10 2zm0 2a6 6 0 1 1 0 12 6 6 0 0 1 0-12z"
					fill="currentColor"
				/></svg
			>
			<input
				id="story-search"
				type="search"
				placeholder="Search your stories"
				bind:value={query}
				autocomplete="off"
			/>
		</div>
		<main
			class="list"
			bind:this={scroller}
			ontouchstart={touchstart}
			ontouchmove={touchmove}
			ontouchend={touchend}
		>
			{#if pulling > 0}
				<div class="pull" style:height="{pulling}px" aria-hidden="true">
					<span class:ready={pulling > 60}
						>{pulling > 60 ? 'Let go to refresh' : 'Pull to refresh'}</span
					>
				</div>
			{/if}
			<StoryList {query} />
		</main>
		<a class="fab" href="/new" aria-label="New story">+</a>
		<Tabs />
	</div>
{/if}

<style>
	.workspace {
		height: 100%;
		display: grid;
		grid-template-columns: 300px minmax(0, 1fr);
	}
	.pick {
		display: grid;
		place-items: center;
		padding: 24px;
	}
	.pick a {
		font-weight: 600;
		text-decoration: none;
	}
	.screen {
		height: 100%;
		display: flex;
		flex-direction: column;
	}
	.avatar {
		width: 34px;
		height: 34px;
		border-radius: 50%;
		background: var(--gold-soft);
		color: var(--gold-text);
		display: grid;
		place-items: center;
		font-weight: 600;
		font-size: 0.85rem;
		text-decoration: none;
	}
	/* On a wide screen the section nav has You; the avatar is the phone's way there. */
	@media (min-width: 900px) {
		.avatar {
			display: none;
		}
	}
	.search {
		margin: 10px 14px 8px;
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 0 14px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--line);
		color: var(--muted);
	}
	.search:focus-within {
		border-color: var(--gold);
	}
	.search input {
		flex: 1;
		background: transparent;
		border: 0;
		outline: none;
		color: var(--fg);
		min-height: 42px;
		font-size: 0.95rem;
	}
	.list {
		flex: 1;
		min-height: 0;
		overflow: auto;
		padding: 0 12px 96px;
		display: grid;
		gap: 6px;
		align-content: start;
		overscroll-behavior: contain;
	}
	.pull {
		display: grid;
		place-items: center;
		color: var(--muted);
		font-size: 0.75rem;
		overflow: hidden;
	}
	.pull .ready {
		color: var(--gold-text);
	}
	.fab {
		position: fixed;
		right: 18px;
		bottom: calc(78px + var(--safe-bottom));
		width: 56px;
		height: 56px;
		border-radius: 18px;
		background: var(--gold);
		color: var(--gold-ink);
		display: grid;
		place-items: center;
		font-size: 1.8rem;
		font-weight: 500;
		text-decoration: none;
		box-shadow: 0 10px 30px var(--gold-glow);
		z-index: 5;
	}
	@media (min-width: 900px) {
		.fab {
			bottom: 26px;
			right: calc(50% - var(--frame) / 2 + 18px);
		}
	}
</style>
