<script lang="ts">
	import { slide } from 'svelte/transition';
	import DialControl from '#lib/DialControl.svelte';
	import type { Extras } from '#lib/extras.svelte.ts';
	import MetersPanel from '#lib/MetersPanel.svelte';
	import PromptPanel from '#lib/PromptPanel.svelte';
	import StatusPanel from '#lib/StatusPanel.svelte';

	/** Beside the conversation: the dials, the meters, the status, the last prompt and the running
	 * cost. A column on the desktop (`compact`), the Dials sheet on a phone. A dial the reader has
	 * set is a control; one still following the card is a single line that opens in place. */
	let {
		extras,
		section = $bindable('dials'),
		compact = false
	}: { extras: Extras; section?: Section; compact?: boolean } = $props();

	type Section = 'dials' | 'meters' | 'status' | 'prompt';
	const sections = $derived<{ id: Section; label: string; count?: number }[]>([
		{ id: 'dials', label: 'Dials' },
		{ id: 'meters', label: 'Meters', count: extras.trackers.length || undefined },
		{ id: 'status', label: 'Status' },
		{ id: 'prompt', label: 'Prompt' }
	]);

	// --- dials --------------------------------------------------------------------------------
	const enabledDials = $derived(extras.dials.filter((d) => d.enabled));
	const setDials = $derived(enabledDials.filter((d) => d.stored !== null));
	const unsetDials = $derived(enabledDials.filter((d) => d.stored === null));
	/** The unset dial opened to its full control. */
	let expanded = $state<string | null>(null);

	function clear(key: string) {
		if (expanded === key) expanded = null;
		void extras.clearDial(key);
	}
</script>

<div class="rail" class:compact>
	<nav class="tabs" class:compact aria-label="Story panel">
		{#each sections as s (s.id)}
			<button type="button" class:on={section === s.id} onclick={() => (section = s.id)}
				>{s.label}{#if s.count}<span class="count">{s.count}</span>{/if}</button
			>
		{/each}
	</nav>

	<div class="body" class:compact>
		{#if !extras.loaded}
			<p class="muted small">Reading…</p>
		{:else if section === 'dials'}
			<div class="stack big">
				{#if compact}
					<p class="muted lead">Saved as you touch them; reach the story from its next turn.</p>
				{/if}
				{#each setDials as sd (sd.key)}
					{@const dial = extras.dial(sd.key)}
					{#if dial}
						<DialControl
							{dial}
							setting={sd}
							{compact}
							onset={(value) => extras.setDial(sd.key, value)}
							onclear={() => clear(sd.key)}
						/>
					{/if}
				{/each}
				{#if unsetDials.length > 0}
					<div class="unset">
						<h4>Not set · following the card</h4>
						{#each unsetDials as sd (sd.key)}
							{@const dial = extras.dial(sd.key)}
							{#if dial}
								{#if expanded === sd.key}
									<div class="open" transition:slide={{ duration: 150 }}>
										<DialControl
											{dial}
											setting={sd}
											{compact}
											onset={(value) => {
												expanded = null;
												void extras.setDial(sd.key, value);
											}}
											onclear={() => clear(sd.key)}
											oncollapse={() => (expanded = null)}
										/>
									</div>
								{:else}
									<button type="button" class="row" onclick={() => (expanded = sd.key)}>
										<span>{dial.title}</span><span class="set">Set ›</span>
									</button>
								{/if}
							{/if}
						{/each}
					</div>
				{/if}
				{#if !compact}
					<p class="muted small">
						A dial reaches the prompt or the sampler from the next turn, never the transcript. This
						story only.
					</p>
				{/if}
			</div>
		{:else if section === 'meters'}
			<MetersPanel {extras} />
		{:else if section === 'status'}
			<StatusPanel {extras} />
		{:else}
			<PromptPanel {extras} />
		{/if}
	</div>
</div>

<style>
	.rail.compact {
		height: 100%;
		display: flex;
		flex-direction: column;
		gap: 0;
	}
	.rail.compact .tabs {
		margin: 12px 16px 0;
		flex: none;
	}
	.body {
		display: grid;
		gap: 14px;
		align-content: start;
		min-width: 0;
	}
	.body.compact {
		flex: 1;
		min-height: 0;
		overflow: auto;
		padding: 14px 16px 16px;
		gap: 18px;
	}
	.rail {
		display: grid;
		gap: 14px;
		align-content: start;
		min-width: 0;
	}
	.tabs {
		display: flex;
		gap: 2px;
		padding: 3px;
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
		font-size: 0.8rem;
		font-weight: 500;
		padding: 6px 8px;
		min-height: 34px;
		border-radius: var(--r-pill);
	}
	.tabs.compact button {
		min-height: 32px;
	}
	.tabs button.on {
		background: var(--gold);
		color: var(--gold-ink);
	}
	.count {
		margin-left: 5px;
		opacity: 0.7;
		font-weight: 400;
	}
	.lead {
		font-size: 0.76rem;
		line-height: 1.4;
	}
	.unset {
		display: grid;
		gap: 2px;
		border-top: 1px solid var(--line);
		padding-top: 12px;
	}
	.unset h4 {
		font-size: 0.7rem;
		margin-bottom: 6px;
	}
	.unset .row {
		appearance: none;
		border: 0;
		background: transparent;
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 8px 0;
		min-height: 40px;
		color: var(--fg);
		font-size: 0.9rem;
		text-align: left;
	}
	.unset .row:hover {
		color: var(--gold-text);
	}
	.unset .set {
		color: var(--muted);
		font-size: 0.8rem;
	}
	.unset .row:hover .set {
		color: inherit;
	}
	.open {
		padding: 8px 0 12px;
	}
	.stack {
		display: grid;
		gap: 12px;
	}
	.stack.big {
		gap: 20px;
	}
	.small {
		font-size: 0.8rem;
	}
	h4 {
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
		font-weight: 600;
	}
</style>
