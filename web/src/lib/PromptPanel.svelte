<script lang="ts">
	import { fade, layerLabel, shares } from '#lib/audit.ts';
	import type { Extras } from '#lib/extras.svelte.ts';
	import { money } from '#lib/money.ts';
	import Sheet from '#lib/Sheet.svelte';
	import { api } from '#lib/api.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	/** The Prompt tab: what the last reply was built from, layer by layer as one stacked bar over
	 * the budget, what it cost, and two things to do about the story's memory. */
	let { extras }: { extras: Extras } = $props();

	const ctx = $derived(extras.context);
	const bar = $derived(ctx ? shares(ctx) : []);
	const turn = $derived(extras.audit?.turns[0]);
	const setDials = $derived(extras.dials.filter((d) => d.enabled && d.stored !== null).length);

	/** What a layer's name is followed by: the count of what went into it, or what was dropped. */
	function note(name: string, dropped: number): { text: string; warn: boolean } | null {
		if (dropped > 0) return { text: `${dropped} dropped`, warn: true };
		if (name === 'directives' && setDials > 0)
			return { text: `${setDials} ${setDials === 1 ? 'dial' : 'dials'}`, warn: false };
		if (name === 'world' && extras.facts.length > 0)
			return {
				text: `${extras.facts.length} ${extras.facts.length === 1 ? 'fact' : 'facts'}`,
				warn: false
			};
		return null;
	}

	// --- memory ---------------------------------------------------------------------------------
	let confirming = $state(false);
	let rebuilding = $state(false);
	let factsOpen = $state(false);

	async function rebuild() {
		rebuilding = true;
		try {
			const done = await api.rebuildMemory(extras.storyId);
			toasts.show(
				'ok',
				'Memory rebuilt',
				`${done.summaries_written} summaries and ${done.facts_extracted} facts from ${done.messages_covered} messages.`
			);
			await extras.refresh();
		} catch (error) {
			toasts.show(
				'danger',
				'Could not rebuild the memory',
				error instanceof Error ? error.message : undefined
			);
		} finally {
			rebuilding = false;
			confirming = false;
		}
	}

	/** The live facts, grouped by who or what they are about. */
	const bySubject = $derived.by(() => {
		const groups = new Map<string, typeof extras.facts>();
		for (const fact of extras.facts) {
			groups.set(fact.subject, [...(groups.get(fact.subject) ?? []), fact]);
		}
		return [...groups];
	});
</script>

<div class="prompt">
	{#if ctx}
		<div class="top">
			<div class="eyebrow-row">
				<h4>The last prompt{turn ? ` · turn ${turn.sequence}` : ''}</h4>
				<span class="mono total"
					>{ctx.total.toLocaleString()}{ctx.budget ? ` / ${ctx.budget.toLocaleString()}` : ''}</span
				>
			</div>
			<div class="stack" role="img" aria-label="The prompt's layers, by size">
				{#each ctx.layers as layer, i (layer.name)}
					<i
						style:width="{bar[i]}%"
						style:opacity={fade(i, ctx.layers.length)}
						title="{layerLabel(layer.name)} {layer.tokens.toLocaleString()}"
					></i>
				{/each}
			</div>
		</div>
		<dl class="layers">
			{#each ctx.layers as layer (layer.name)}
				{@const extra = note(layer.name, layer.dropped)}
				<dt>
					{layerLabel(layer.name)}
					{#if extra}<span class:warn={extra.warn} class="muted"> · {extra.text}</span>{/if}
				</dt>
				<dd class="mono">{layer.tokens.toLocaleString()}</dd>
			{/each}
		</dl>
		{#if turn?.prompt_tokens}
			<p class="muted line">
				Billed {turn.prompt_tokens.toLocaleString()} prompt tokens{extras.spend?.cached_share !==
					null && extras.spend?.cached_share !== undefined
					? ` · ${Math.round(extras.spend.cached_share * 100)}% served from cache`
					: ''}.
			</p>
		{/if}
	{:else}
		<p class="muted line">
			No reply yet. After the first one, this shows what the prompt was built from.
		</p>
	{/if}

	{#if extras.spend}
		<div class="story">
			<h4>This story</h4>
			<div class="cost">
				<span>Calls</span><b>{extras.spend.calls}</b>
				<span>Cost</span><b>{money(extras.spend.cost)}</b>
				<span>Rerolled away</span><b class="warn">{money(extras.spend.discarded_cost)}</b>
				{#if extras.spend.unpriced}<span>Unpriced calls</span><b>{extras.spend.unpriced}</b>{/if}
				{#if extras.spend.cached_share !== null}
					<span>Cached share</span><b>{Math.round(extras.spend.cached_share * 100)}%</b>
				{/if}
			</div>
			{#if confirming}
				<div class="ask" role="alertdialog" aria-label="Rebuild the memory?">
					<p>
						Throws away this story's summaries and extracted facts and writes them again from the
						transcript. Facts you pinned stay. It calls the model many times, and is billed.
					</p>
					<div class="two">
						<button
							type="button"
							class="chip"
							disabled={rebuilding}
							onclick={() => (confirming = false)}>Keep it</button
						>
						<button type="button" class="chip go" disabled={rebuilding} onclick={rebuild}
							>{rebuilding ? 'Rebuilding…' : 'Rebuild'}</button
						>
					</div>
				</div>
			{:else}
				<div class="chips">
					<button type="button" class="chip" onclick={() => (confirming = true)}
						>Rebuild memory</button
					>
					<button type="button" class="chip" onclick={() => (factsOpen = true)}
						>Facts · {extras.facts.length}</button
					>
				</div>
			{/if}
		</div>
	{/if}
</div>

<Sheet
	bind:open={factsOpen}
	title="What the story believes"
	hint="{extras.facts.length} {extras.facts.length === 1 ? 'fact' : 'facts'}"
>
	{#if bySubject.length === 0}
		<p class="muted">Nothing yet. Facts appear as the story is played.</p>
	{:else}
		<div class="facts">
			{#each bySubject as [subject, facts] (subject)}
				<section>
					<h4>{subject}</h4>
					{#each facts as fact (fact.id)}
						<p>
							{fact.text}
							<span class="muted from"
								>from turn {fact.valid_from_sequence}{fact.pinned ? ' · pinned' : ''}</span
							>
						</p>
					{/each}
				</section>
			{/each}
		</div>
	{/if}
</Sheet>

<style>
	.prompt {
		display: grid;
		gap: 16px;
		align-content: start;
		min-width: 0;
	}
	h4 {
		font-size: 0.7rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
		font-weight: 600;
	}
	.top {
		display: grid;
		gap: 4px;
	}
	.eyebrow-row {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 10px;
	}
	.mono {
		font-family: var(--font-mono);
	}
	.total {
		font-size: 0.76rem;
		color: var(--muted);
	}
	.stack {
		display: flex;
		height: 10px;
		border-radius: 5px;
		overflow: hidden;
		background: var(--surface-2);
		gap: 1px;
	}
	.stack i {
		display: block;
		background: var(--gold-2);
		min-width: 2px;
	}
	.layers {
		margin: 0;
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 6px 10px;
		font-size: 0.84rem;
		color: var(--fg-2);
		font-variant-numeric: tabular-nums;
	}
	dt,
	dd {
		margin: 0;
	}
	dd {
		font-size: 0.78rem;
	}
	.warn {
		color: var(--warn);
	}
	.line {
		font-size: 0.76rem;
		line-height: 1.4;
	}
	.story {
		border-top: 1px solid var(--line);
		padding-top: 14px;
		display: grid;
		gap: 8px;
	}
	.cost {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 4px 12px;
		font-size: 0.88rem;
		color: var(--fg-2);
		font-variant-numeric: tabular-nums;
	}
	.cost b {
		font-weight: 600;
		color: var(--fg);
	}
	.cost .warn {
		color: var(--warn);
	}
	.chips {
		display: flex;
		gap: 6px;
		flex-wrap: wrap;
		padding-top: 4px;
	}
	.chip {
		appearance: none;
		display: inline-flex;
		align-items: center;
		padding: 5px 11px;
		border-radius: var(--r-pill);
		font-size: 0.78rem;
		font-weight: 500;
		background: var(--surface-2);
		color: var(--fg-2);
		border: 1px solid var(--line);
	}
	.chip:hover:not(:disabled) {
		color: var(--fg);
		border-color: var(--line-strong);
	}
	.chip.go {
		background: var(--gold);
		color: var(--gold-ink);
		border-color: transparent;
	}
	.chip:disabled {
		opacity: 0.6;
	}
	.ask {
		display: grid;
		gap: 10px;
		padding: 10px 12px;
		border-radius: 12px;
		border: 1px solid var(--line-strong);
		font-size: 0.8rem;
		color: var(--fg-2);
		line-height: 1.4;
	}
	.two {
		display: flex;
		gap: 6px;
	}
	.facts {
		display: grid;
		gap: 14px;
	}
	.facts section {
		display: grid;
		gap: 6px;
	}
	.facts p {
		font-size: 0.92rem;
		line-height: 1.4;
	}
	.from {
		font-size: 0.72rem;
		white-space: nowrap;
	}
</style>
