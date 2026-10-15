<script lang="ts">
	import type { Tracker } from '#lib/api.ts';
	import { debounce } from '#lib/debounce.ts';
	import type { Extras } from '#lib/extras.svelte.ts';

	/** The Meters tab: a card for each number the story keeps, adjusted in place (a slider and two
	 * steppers, saved a moment after the last touch), and a card to add one more. */
	let { extras }: { extras: Extras } = $props();

	/** The meter being adjusted, and the value on screen while the slider is moving. */
	let adjusting = $state<string | null>(null);
	let draft = $state(0);

	const save = debounce((name: string, value: number) => void extras.setTracker(name, value), 300);

	function adjust(t: Tracker) {
		save.flush();
		adjusting = t.name;
		draft = t.value;
	}

	function move(t: Tracker, value: number) {
		draft = Math.min(t.max, Math.max(0, value));
		save(t.name, draft);
	}

	function done() {
		save.flush();
		adjusting = null;
	}

	function remove(t: Tracker) {
		save.cancel();
		adjusting = null;
		void extras.removeTracker(t.name);
	}

	// --- a new meter ---------------------------------------------------------------------------
	let name = $state('');
	let start = $state(0);
	let max = $state(100);
	let means = $state('');

	async function add(event: SubmitEvent) {
		event.preventDefault();
		if (!name.trim()) return;
		const ok = await extras.addTracker({
			name: name.trim(),
			value: start,
			max,
			means: means.trim() || null
		});
		if (ok) {
			name = '';
			start = 0;
			max = 100;
			means = '';
		}
	}

	function bar(value: number, maximum: number): number {
		return maximum > 0 ? Math.min(100, Math.max(0, (value / maximum) * 100)) : 0;
	}

	function trim(n: number): string {
		return Number.isInteger(n) ? String(n) : n.toFixed(1);
	}
</script>

<div class="meters">
	<p class="muted intro">
		A number the story keeps. The model moves it a little each reply; you can move it by hand.
	</p>

	{#each extras.trackers as t (t.id)}
		{@const live = adjusting === t.name ? draft : t.value}
		<div class="meter" class:on={adjusting === t.name}>
			<div class="head">
				<b>{t.name}</b>
				<span class="mono">
					{trim(live)}/{trim(t.max)}
					{#if t.delta !== 0}
						<span class:up={t.delta > 0} class:down={t.delta < 0}
							>{t.delta > 0 ? '+' : ''}{trim(t.delta)}</span
						>
					{/if}
				</span>
			</div>
			<div class="bar"><i style:width="{bar(live, t.max)}%"></i></div>
			{#if adjusting === t.name}
				<div class="adjust">
					<button
						type="button"
						class="step"
						aria-label="Less {t.name}"
						onclick={() => move(t, draft - 1)}>−</button
					>
					<input
						type="range"
						min="0"
						max={t.max}
						step="1"
						value={draft}
						aria-label={t.name}
						oninput={(e) => move(t, Number(e.currentTarget.value))}
					/>
					<button
						type="button"
						class="step"
						aria-label="More {t.name}"
						onclick={() => move(t, draft + 1)}>+</button
					>
				</div>
				<div class="foot">
					<span class="muted">{t.means ?? '—'}</span>
					<span class="acts">
						<button type="button" class="link danger" onclick={() => remove(t)}>Remove</button>
						<button type="button" class="link" onclick={done}>Done</button>
					</span>
				</div>
			{:else}
				<div class="foot">
					<span class="muted"
						>{t.note ?? t.means ?? '—'}{t.updated_at_sequence
							? ` · turn ${t.updated_at_sequence}`
							: ''}</span
					>
					<button type="button" class="link" onclick={() => adjust(t)}>Adjust</button>
				</div>
			{/if}
		</div>
	{/each}

	<form class="meter add" onsubmit={add}>
		<b>New meter</b>
		<label class="field"
			><span>Name</span><input
				class="input"
				id="meter-name"
				type="text"
				bind:value={name}
				maxlength="120"
				required
				placeholder="Trust"
			/></label
		>
		<div class="two">
			<label class="field"
				><span>Starts at</span><input
					class="input"
					id="meter-start"
					type="number"
					step="any"
					min="0"
					bind:value={start}
				/></label
			>
			<label class="field"
				><span>Out of</span><input
					class="input"
					id="meter-max"
					type="number"
					step="any"
					min="1"
					bind:value={max}
				/></label
			>
		</div>
		<label class="field"
			><span>What it measures</span><input
				class="input"
				id="meter-means"
				type="text"
				bind:value={means}
				maxlength="500"
				placeholder="how far she trusts Rowan"
			/></label
		>
		<button type="submit" class="btn primary">Add meter</button>
	</form>
</div>

<style>
	.meters {
		display: grid;
		gap: 12px;
		min-width: 0;
	}
	.intro {
		font-size: 0.76rem;
		line-height: 1.4;
	}
	.meter {
		display: grid;
		gap: 8px;
		padding: 12px;
		border-radius: 12px;
		background: var(--surface);
		border: 1px solid var(--line);
	}
	.meter.on {
		border-color: var(--gold);
		box-shadow: 0 0 0 3px var(--gold-soft);
	}
	.head {
		display: flex;
		justify-content: space-between;
		gap: 10px;
		align-items: baseline;
	}
	.head b {
		font-weight: 600;
	}
	.mono {
		font-family: var(--font-mono);
		font-size: 0.8rem;
	}
	.up {
		color: var(--ok);
	}
	.down {
		color: var(--danger);
	}
	.bar {
		height: 8px;
		border-radius: 4px;
		background: var(--surface-2);
		overflow: hidden;
	}
	.bar i {
		display: block;
		height: 100%;
		border-radius: 4px;
		background: linear-gradient(90deg, var(--gold-2), var(--gold));
		transition: width 0.3s ease;
	}
	.foot {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		align-items: center;
		font-size: 0.75rem;
	}
	.acts {
		display: flex;
		gap: 4px;
	}
	.link {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--gold-text);
		font-weight: 600;
		font-size: 0.75rem;
		padding: 6px 8px;
		min-height: 32px;
	}
	.link.danger {
		color: var(--danger);
	}
	.adjust {
		display: grid;
		grid-template-columns: 40px 1fr 40px;
		gap: 8px;
		align-items: center;
	}
	.step {
		appearance: none;
		width: 40px;
		height: 40px;
		border-radius: 50%;
		border: 1px solid var(--line-strong);
		background: var(--surface-2);
		color: var(--fg);
		font-size: 1.2rem;
		line-height: 1;
	}
	input[type='range'] {
		width: 100%;
		accent-color: var(--gold);
	}
	.add {
		border-style: dashed;
		border-color: var(--line-strong);
		background: transparent;
		gap: 10px;
	}
	.add b {
		font-weight: 600;
		font-size: 0.9rem;
	}
	.two {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 8px;
	}
	.add .btn {
		min-height: 38px;
	}
</style>
