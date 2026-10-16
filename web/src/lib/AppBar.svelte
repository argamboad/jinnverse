<script lang="ts">
	import type { Snippet } from 'svelte';
	import Lamp from '#lib/Lamp.svelte';
	import SectionNav from '#lib/SectionNav.svelte';

	/** The bar at the top of a screen: a back arrow or the mark, a title with a line under it,
	 * the top-level sections (on a wide screen; the phone has its tabs), and whatever actions the
	 * screen puts on the right. The same shape on every screen. */
	let {
		title,
		sub,
		back,
		mark = false,
		ontitle,
		titleOpen = false,
		sections = true,
		actions
	}: {
		title: string;
		sub?: string;
		back?: string;
		mark?: boolean;
		/** Makes the title block a button (the story's own sheet opens from it). */
		ontitle?: () => void;
		/** The thing `ontitle` opens is showing: the block is lit and the arrow points up. */
		titleOpen?: boolean;
		/** The section pills on a wide screen; off where a rail beside the screen does their job. */
		sections?: boolean;
		actions?: Snippet;
	} = $props();
</script>

<header class="bar">
	{#if back}
		<a class="back" href={back} aria-label="Back">‹</a>
	{:else if mark}
		<Lamp size={30} />
	{/if}
	{#if ontitle}
		<button
			type="button"
			class="title tap"
			class:open={titleOpen}
			aria-haspopup="dialog"
			aria-expanded={titleOpen}
			onclick={ontitle}
		>
			<span class="line">
				<h1>{title}</h1>
				<span class="caret" aria-hidden="true">{titleOpen ? '⌃' : '⌄'}</span>
			</span>
			{#if sub}<span class="sub">{sub}</span>{/if}
		</button>
	{:else}
		<div class="title">
			<h1>{title}</h1>
			{#if sub}<span class="sub">{sub}</span>{/if}
		</div>
	{/if}
	<div class="grow"></div>
	{#if actions}{@render actions()}{/if}
	{#if sections}<SectionNav />{/if}
</header>

<style>
	.bar {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: calc(6px + var(--safe-top)) 12px 6px;
		position: sticky;
		top: 0;
		z-index: 10;
		background: color-mix(in srgb, var(--bg) 86%, transparent);
		backdrop-filter: blur(14px);
		border-bottom: 1px solid var(--line);
		min-height: 48px;
	}
	.back {
		text-decoration: none;
		color: var(--fg-2);
		font-size: 1.7rem;
		line-height: 1;
		width: 36px;
		height: 36px;
		display: grid;
		place-items: center;
		border-radius: 50%;
		margin-left: -8px;
	}
	.title {
		min-width: 0;
		display: grid;
	}
	.tap {
		appearance: none;
		border: 0;
		background: transparent;
		color: inherit;
		text-align: left;
		padding: 4px 6px;
		margin-left: -6px;
		border-radius: var(--r-s);
	}
	.tap.open {
		background: var(--gold-soft);
	}
	.line {
		display: flex;
		align-items: center;
		gap: 6px;
		min-width: 0;
	}
	.caret {
		flex: none;
		color: var(--muted);
		font-size: 0.8rem;
	}
	h1 {
		font-size: 1.05rem;
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.sub {
		font-size: 0.74rem;
		color: var(--muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.grow {
		flex: 1;
	}
	/* On a wide screen every bar is as tall as the tallest (a title with a second line), so the section
	   nav sits at the same height everywhere. Phones keep their compact bars. */
	@media (min-width: 900px) {
		.bar {
			min-height: 62px;
		}
	}
</style>
