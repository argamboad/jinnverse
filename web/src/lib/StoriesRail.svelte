<script lang="ts">
	import { onMount } from 'svelte';
	import Lamp from '#lib/Lamp.svelte';
	import StoryList from '#lib/StoryList.svelte';
	import { stories } from '#lib/stories.svelte.ts';

	/** The workspace's left rail: the mark, the Stories / Library switch, the way to You, a search,
	 * every story as a row (the open one marked) and the way to start another. */
	let { current }: { current?: string } = $props();

	let query = $state('');

	onMount(() => {
		if (stories.list === null) void stories.refresh();
	});
</script>

<aside class="rail" aria-label="Stories">
	<div class="head">
		<Lamp size={30} />
		<nav class="seg" aria-label="Sections">
			<a href="/" aria-current="page" class="on">Stories</a>
			<a href="/library">Library</a>
		</nav>
		<div class="grow"></div>
		<a class="avatar" href="/you" aria-label="You">R</a>
	</div>
	<div class="search">
		<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"
			><path
				d="M10 2a8 8 0 1 0 4.9 14.3l5.4 5.4 1.4-1.4-5.4-5.4A8 8 0 0 0 10 2zm0 2a6 6 0 1 1 0 12 6 6 0 0 1 0-12z"
				fill="currentColor"
			/></svg
		>
		<input
			type="search"
			placeholder="Search stories"
			aria-label="Search stories"
			bind:value={query}
			autocomplete="off"
		/>
	</div>
	<div class="list">
		<StoryList {query} {current} rail />
	</div>
	<div class="foot">
		<a class="new btn primary" href="/new">+ New story</a>
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
	.head {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 12px 12px 8px;
		min-height: 62px;
	}
	.grow {
		flex: 1;
	}
	.seg {
		display: flex;
		gap: 2px;
		padding: 3px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--line);
	}
	.seg a {
		text-decoration: none;
		color: var(--fg-2);
		font-weight: 500;
		font-size: 0.85rem;
		padding: 5px 12px;
		border-radius: var(--r-pill);
	}
	.seg a.on {
		background: var(--gold);
		color: var(--gold-ink);
	}
	.avatar {
		width: 32px;
		height: 32px;
		border-radius: 50%;
		background: var(--gold-soft);
		color: var(--gold-text);
		display: grid;
		place-items: center;
		font-weight: 600;
		font-size: 0.8rem;
		text-decoration: none;
	}
	.search {
		margin: 0 12px 8px;
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 0 12px;
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
		min-width: 0;
		background: transparent;
		border: 0;
		outline: none;
		color: var(--fg);
		min-height: 36px;
		font-size: 0.9rem;
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
