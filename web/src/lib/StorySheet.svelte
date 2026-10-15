<script lang="ts">
	import type { ExportFormat, Story, StorySpend } from '#lib/api.ts';
	import { exportFormats, exportStory } from '#lib/exportStory.ts';
	import { money } from '#lib/money.ts';
	import Sheet from '#lib/Sheet.svelte';

	/** The story's own sheet, opened from its title: its name (saved when the field is left),
	 * who it is with, what it has cost, and what can be done to the whole of it. */
	let {
		open = $bindable(false),
		story,
		spend,
		canBranch,
		onrename,
		onbranch,
		ondelete
	}: {
		open?: boolean;
		story: Story | null;
		spend: StorySpend | null;
		/** There is a reply to branch from. */
		canBranch: boolean;
		onrename: (name: string) => void;
		onbranch: () => void;
		ondelete: () => void;
	} = $props();

	let name = $state('');
	let choosing = $state(false);
	let confirming = $state(false);

	// Each opening starts from the story as it is: the name filled in, nothing half-chosen.
	$effect(() => {
		if (open) {
			name = story?.name ?? '';
			choosing = false;
			confirming = false;
		}
	});

	function commitName() {
		const next = name.trim();
		if (!story) return;
		if (!next) name = story.name;
		else if (next !== story.name) onrename(next);
	}

	async function save(format: ExportFormat) {
		if (!story) return;
		open = false;
		await exportStory(story.id, format);
	}

	const spent = $derived.by(() => {
		if (!spend) return '—';
		const parts = [money(spend.cost), `${spend.calls} ${spend.calls === 1 ? 'call' : 'calls'}`];
		if (Number(spend.discarded_cost) > 0)
			parts.push(`${money(spend.discarded_cost)} rerolled away`);
		return parts.join(' · ');
	});
</script>

<Sheet bind:open title={story?.name ?? 'Story'} bare>
	{#if story}
		<label class="field">
			<span>Name</span>
			<input
				class="input"
				id="story-name"
				type="text"
				bind:value={name}
				maxlength="200"
				onblur={commitName}
				onkeydown={(e) => {
					if (e.key === 'Enter') e.currentTarget.blur();
				}}
			/>
			<small class="muted">Saved when you leave the field.</small>
		</label>

		<dl class="facts">
			<dt>With</dt>
			<dd>
				<span>{story.character_name}</span>
				<a href="/library/characters/{story.character_id}">open ›</a>
			</dd>
			<dt>As</dt>
			<dd>
				<span>{story.persona_name ?? 'no persona'}</span>
				{#if story.persona_id}<a href="/library/personas/{story.persona_id}">open ›</a>{/if}
			</dd>
			<dt>Spent</dt>
			<dd class="mono">{spent}</dd>
		</dl>

		<div class="menu">
			{#if canBranch}
				<button type="button" class="btn" onclick={onbranch}>Branch from the end</button>
			{/if}
			{#if choosing}
				<div class="choice" role="group" aria-label="Export as">
					{#each exportFormats as f (f.id)}
						<button type="button" class="btn" onclick={() => save(f.id)}>{f.label}</button>
					{/each}
					<button type="button" class="btn ghost" onclick={() => (choosing = false)}>Back</button>
				</div>
			{:else}
				<button type="button" class="btn" onclick={() => (choosing = true)}
					>Export · Markdown, JSON, text</button
				>
			{/if}
			{#if confirming}
				<p class="muted">Delete “{story.name}”? It is hidden, not erased.</p>
				<div class="choice two" role="alertdialog" aria-label="Delete this story?">
					<button type="button" class="btn ghost" onclick={() => (confirming = false)}>Keep</button>
					<button type="button" class="btn danger" onclick={ondelete}>Delete</button>
				</div>
			{:else}
				<button type="button" class="btn ghost danger-text" onclick={() => (confirming = true)}
					>Delete the story</button
				>
			{/if}
		</div>
	{/if}
</Sheet>

<style>
	.field small {
		font-size: 0.74rem;
	}
	.facts {
		margin: 0;
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 6px 14px;
		font-size: 0.92rem;
		align-items: center;
	}
	dt {
		color: var(--muted);
		font-size: 0.82rem;
	}
	dd {
		margin: 0;
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		min-width: 0;
	}
	dd a {
		color: var(--muted);
		font-size: 0.78rem;
		text-decoration: none;
		white-space: nowrap;
	}
	dd.mono {
		font-size: 0.85rem;
		justify-content: flex-start;
	}
	.menu {
		display: grid;
		gap: 8px;
	}
	.choice {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 8px;
	}
	.btn.danger {
		background: var(--danger);
		color: #fff;
	}
	.btn.danger-text {
		color: var(--danger);
	}
</style>
