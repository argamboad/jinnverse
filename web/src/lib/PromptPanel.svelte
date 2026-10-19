<script lang="ts">
	import { fade, layerLabel, shares } from '#lib/audit.ts';
	import type { Extras } from '#lib/extras.svelte.ts';
	import { fine, money } from '#lib/money.ts';
	import Sheet from '#lib/Sheet.svelte';
	import { api, type Condensed, type Reviewed } from '#lib/api.ts';
	import { condensePlan, confirmed, subjectOf, tally } from '#lib/review.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	/** The Prompt tab: what the last reply was built from, layer by layer as one stacked bar over
	 * the budget, what it cost, and the memory tools — each billed, each asking first with the
	 * cost, and Review facts applying nothing the reader did not keep. */
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
	// One confirm at a time. Review and Condense open theirs with a dry run, so the confirm can
	// say the number before anything is billed; Rebuild has no estimate (many calls).
	type Tool = 'rebuild' | 'review' | 'condense';
	let asking = $state<Tool | null>(null);
	let busy = $state(false);
	let factsOpen = $state(false);
	let reviewEstimate = $state<string | null>(null);
	let condenseEstimate = $state<Condensed | null>(null);
	let reviewed = $state<Reviewed | null>(null);
	let reviewOpen = $state(false);
	let kept = $state<boolean[]>([]);
	let applying = $state(false);

	function failed(title: string, error: unknown) {
		toasts.show('danger', title, error instanceof Error ? error.message : undefined);
	}

	async function ask(tool: Tool) {
		busy = true;
		try {
			if (tool === 'review') {
				reviewEstimate = (await api.reviewFacts(extras.storyId, true)).estimated_cost;
			} else if (tool === 'condense') {
				condenseEstimate = await api.condense(extras.storyId, undefined, true);
			}
			asking = tool;
		} catch (error) {
			failed(tool === 'review' ? 'Could not estimate the review' : 'Nothing to condense', error);
		} finally {
			busy = false;
		}
	}

	async function rebuild() {
		busy = true;
		try {
			const done = await api.rebuildMemory(extras.storyId);
			toasts.show(
				'ok',
				'Memory rebuilt',
				`${done.summaries_written} summaries and ${done.facts_extracted} facts from ${done.messages_covered} messages.`
			);
			await extras.refresh();
		} catch (error) {
			failed('Could not rebuild the memory', error);
		} finally {
			busy = false;
			asking = null;
		}
	}

	async function review() {
		busy = true;
		try {
			const answer = await api.reviewFacts(extras.storyId);
			await extras.refresh();
			if (answer.proposals.length === 0) {
				toasts.show('ok', 'Nothing to change', 'The model proposes no change to the facts.');
				return;
			}
			reviewed = answer;
			kept = answer.proposals.map(() => true);
			reviewOpen = true;
		} catch (error) {
			failed('The review was not made', error);
		} finally {
			busy = false;
			asking = null;
		}
	}

	async function apply() {
		if (!reviewed) return;
		const set = confirmed(reviewed.proposals, kept);
		applying = true;
		try {
			const done = await api.applyReview(extras.storyId, set);
			toasts.show(
				'ok',
				`Applied ${set.length} ${set.length === 1 ? 'proposal' : 'proposals'}`,
				`${done.retired} ${done.retired === 1 ? 'fact' : 'facts'} retired, ${done.added} added.`
			);
			reviewOpen = false;
			reviewed = null;
			await extras.refresh();
		} catch (error) {
			failed('Nothing was applied', error);
		} finally {
			applying = false;
		}
	}

	async function condense() {
		busy = true;
		try {
			const done = await api.condense(extras.storyId);
			toasts.show(
				'ok',
				'Summaries condensed',
				`${done.summaries} became 1: ${done.tokens_before.toLocaleString()} tokens are now ${done.tokens_after?.toLocaleString() ?? 'fewer'}.`
			);
			await extras.refresh();
		} catch (error) {
			failed('Nothing was condensed', error);
		} finally {
			busy = false;
			asking = null;
		}
	}

	const keptCount = $derived(kept.filter(Boolean).length);

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
			{#if asking === 'review'}
				<div class="ask" role="alertdialog" aria-label="Review the facts?">
					<p>
						Asks the model what to retire, rewrite or merge among the {extras.facts.length} facts, reading
						the story as it does for a reply. One call,
						<b
							>{reviewEstimate !== null
								? `about ${fine(reviewEstimate)}`
								: 'about what a reply costs'}</b
						>. Nothing changes until you confirm each proposal.
					</p>
					<div class="two">
						<button type="button" class="chip" disabled={busy} onclick={() => (asking = null)}
							>Keep them</button
						>
						<button type="button" class="chip go" disabled={busy} onclick={review}
							>{busy
								? 'Reviewing…'
								: `Review${reviewEstimate !== null ? ` · ${fine(reviewEstimate)}` : ''}`}</button
						>
					</div>
				</div>
			{:else if asking === 'condense' && condenseEstimate}
				<div class="ask" role="alertdialog" aria-label="Condense the summaries?">
					<p>
						{condensePlan(condenseEstimate)} The newest summary stays. One call,
						<b
							>{condenseEstimate.estimated_cost !== null
								? `about ${fine(condenseEstimate.estimated_cost)}`
								: 'about what a summary costs'}</b
						>.
					</p>
					<div class="two">
						<button type="button" class="chip" disabled={busy} onclick={() => (asking = null)}
							>Keep them</button
						>
						<button type="button" class="chip go" disabled={busy} onclick={condense}
							>{busy
								? 'Condensing…'
								: `Condense${condenseEstimate.estimated_cost !== null ? ` · ${fine(condenseEstimate.estimated_cost)}` : ''}`}</button
						>
					</div>
				</div>
			{:else if asking === 'rebuild'}
				<div class="ask" role="alertdialog" aria-label="Rebuild the memory?">
					<p>
						Throws away this story's summaries and extracted facts and writes them again from the
						transcript. Facts you pinned stay. It calls the model many times, and is billed.
					</p>
					<div class="two">
						<button type="button" class="chip" disabled={busy} onclick={() => (asking = null)}
							>Keep it</button
						>
						<button type="button" class="chip go" disabled={busy} onclick={rebuild}
							>{busy ? 'Rebuilding…' : 'Rebuild'}</button
						>
					</div>
				</div>
			{:else}
				<div class="chips">
					<button type="button" class="chip" disabled={busy} onclick={() => ask('review')}
						>Review facts</button
					>
					<button type="button" class="chip" disabled={busy} onclick={() => ask('condense')}
						>Condense summaries</button
					>
					<button type="button" class="chip" disabled={busy} onclick={() => (asking = 'rebuild')}
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
	bind:open={reviewOpen}
	title="What the model proposes"
	hint={reviewed
		? `${reviewed.proposals.length} ${reviewed.proposals.length === 1 ? 'proposal' : 'proposals'}${reviewed.cost !== null ? ` · ${fine(reviewed.cost)}` : ''}`
		: undefined}
>
	{#if reviewed}
		<p class="lead">
			Each one is a guess with a reason. Switch off what you don’t agree with; the rest is applied
			at once. Pinned facts are never touched.
		</p>
		<div class="proposals">
			{#each reviewed.proposals as proposal, i (i)}
				<div class="proposal" class:off={!kept[i]}>
					<span class="kind" class:retire={proposal.action === 'retire'}>{proposal.action}</span>
					<label class="switch" class:on={kept[i]}>
						<input type="checkbox" bind:checked={kept[i]} aria-label="Keep this proposal" />
					</label>
					<span class="was">
						{#each proposal.facts as fact, j (fact.id)}
							{#if j > 0}<span class="plus"> + </span>{/if}
							<span class="subject">{fact.subject}</span> · <s>{fact.text}</s>
						{/each}
					</span>
					{#if proposal.text}
						<span class="now"
							><span class="subject">{subjectOf(proposal)}</span> · {proposal.text}</span
						>
					{/if}
					{#if proposal.reason}<span class="why">{proposal.reason}</span>{/if}
				</div>
			{/each}
		</div>
		<div class="foot">
			<span class="muted sum"
				>{tally(kept)}{reviewed.skipped ? ` · ${reviewed.skipped} not shown` : ''}</span
			>
			<div class="two">
				<button type="button" class="chip" disabled={applying} onclick={() => (reviewOpen = false)}
					>Discard</button
				>
				<button type="button" class="chip go" disabled={applying || keptCount === 0} onclick={apply}
					>{applying ? 'Applying…' : `Apply ${keptCount}`}</button
				>
			</div>
		</div>
	{/if}
</Sheet>

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
	.ask b {
		color: var(--fg);
		font-weight: 600;
	}
	/* the proposals: what was there, what it becomes, and why — kept until switched off */
	.lead {
		font-size: 0.8rem;
		color: var(--fg-2);
		line-height: 1.4;
	}
	.proposals {
		display: grid;
		gap: 10px;
	}
	.proposal {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 6px 12px;
		padding: 10px 12px;
		border-radius: 12px;
		background: var(--surface-2);
		border: 1px solid var(--line);
	}
	.proposal.off {
		opacity: 0.55;
	}
	.kind {
		font-size: 0.7rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		font-weight: 600;
		color: var(--gold-text);
	}
	.kind.retire {
		color: var(--warn);
	}
	.was {
		font-size: 0.84rem;
		color: var(--muted);
		line-height: 1.35;
	}
	.was s {
		text-decoration-color: var(--line-strong);
	}
	.now {
		font-size: 0.92rem;
		color: var(--fg);
		line-height: 1.35;
	}
	.why {
		font-size: 0.78rem;
		color: var(--fg-2);
		font-family: var(--font-prose);
		font-style: italic;
		line-height: 1.35;
	}
	.subject {
		font-weight: 600;
		color: var(--fg-2);
	}
	.switch {
		grid-row: 1 / span 4;
		align-self: start;
		position: relative;
		width: 40px;
		height: 24px;
		border-radius: var(--r-pill);
		background: var(--line-strong);
		cursor: pointer;
	}
	.switch.on {
		background: var(--gold);
	}
	.switch input {
		position: absolute;
		inset: 0;
		opacity: 0;
		margin: 0;
		cursor: pointer;
	}
	.switch::after {
		content: '';
		position: absolute;
		top: 3px;
		left: 3px;
		width: 18px;
		height: 18px;
		border-radius: 50%;
		background: var(--raised);
		transition: left 0.12s ease;
	}
	.switch.on::after {
		left: 19px;
		background: var(--gold-ink);
	}
	.switch:focus-within {
		outline: 2px solid var(--gold);
		outline-offset: 2px;
	}
	.foot {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		padding-top: 4px;
		border-top: 1px solid var(--line);
	}
	.sum {
		font-size: 0.78rem;
	}
</style>
