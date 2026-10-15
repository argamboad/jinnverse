<script lang="ts">
	import type { ExportFormat, Story } from '#lib/api.ts';
	import { exportFormats, exportStory } from '#lib/exportStory.ts';

	/** The head of the workspace's right column: the story's name (renamed in place), who it is
	 * with and as, and what can be done to the whole of it. The same things as the story sheet,
	 * for a window wide enough to keep them on screen. */
	let {
		story,
		cardVersion = null,
		canBranch,
		onrename,
		onbranch,
		ondelete
	}: {
		story: Story;
		/** The character's current version, which the story reads; null until it is known. */
		cardVersion?: number | null;
		canBranch: boolean;
		onrename: (name: string) => void;
		onbranch: () => void;
		ondelete: () => void;
	} = $props();

	let renaming = $state(false);
	let name = $state('');
	let choosing = $state(false);
	let confirming = $state(false);
	let renameButton: HTMLButtonElement | undefined = $state();

	/** The workspace's title button lands here. */
	export function focus() {
		renameButton?.focus();
	}

	function beginRename() {
		name = story.name;
		renaming = true;
	}

	function commit() {
		if (!renaming) return;
		renaming = false;
		const next = name.trim();
		if (next && next !== story.name) onrename(next);
	}

	function save(format: ExportFormat) {
		choosing = false;
		void exportStory(story.id, format);
	}

	function focusOnMount(node: HTMLInputElement) {
		node.focus();
		node.select();
	}
</script>

<header class="head">
	<div class="name">
		{#if renaming}
			<input
				class="input"
				type="text"
				aria-label="Story name"
				bind:value={name}
				maxlength="200"
				use:focusOnMount
				onblur={commit}
				onkeydown={(e) => {
					if (e.key === 'Enter') commit();
					if (e.key === 'Escape') renaming = false;
				}}
			/>
		{:else}
			<h2>{story.name}</h2>
			<button type="button" class="text" bind:this={renameButton} onclick={beginRename}
				>Rename</button
			>
		{/if}
	</div>
	<dl class="facts">
		<dt>With</dt>
		<dd>
			<a href="/library/characters/{story.character_id}">{story.character_name}</a>
			{#if cardVersion}<span class="muted card">· card v{cardVersion}</span>{/if}
		</dd>
		<dt>As</dt>
		<dd>
			{#if story.persona_id}<a href="/library/personas/{story.persona_id}">{story.persona_name}</a
				>{:else}<span class="muted">{story.persona_name ?? 'no persona'}</span>{/if}
		</dd>
	</dl>
	<div class="chips">
		{#if confirming}
			<span class="ask">Delete it? Hidden, not erased.</span>
			<button type="button" class="chip" onclick={() => (confirming = false)}>Keep</button>
			<button type="button" class="chip danger" onclick={ondelete}>Delete</button>
		{:else if choosing}
			{#each exportFormats as f (f.id)}
				<button type="button" class="chip" onclick={() => save(f.id)}>{f.label}</button>
			{/each}
			<button type="button" class="chip" onclick={() => (choosing = false)}>Back</button>
		{:else}
			{#if canBranch}
				<button type="button" class="chip" onclick={onbranch}>Branch from the end</button>
			{/if}
			<button type="button" class="chip" onclick={() => (choosing = true)}>Export</button>
			<button type="button" class="chip danger" onclick={() => (confirming = true)}>Delete</button>
		{/if}
	</div>
</header>

<style>
	.head {
		padding: 14px 16px 10px;
		border-bottom: 1px solid var(--line);
		display: grid;
		gap: 10px;
	}
	.name {
		display: flex;
		align-items: center;
		gap: 8px;
		min-height: 30px;
	}
	h2 {
		font-size: 0.95rem;
		font-weight: 600;
		flex: 1;
		min-width: 0;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.name .input {
		min-height: 34px;
		padding: 6px 10px;
		font-size: 0.92rem;
	}
	.text {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--gold-text);
		font-weight: 600;
		font-size: 0.78rem;
		padding: 4px 8px;
		min-height: 30px;
		border-radius: var(--r-pill);
	}
	.facts {
		margin: 0;
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 4px 12px;
		font-size: 0.82rem;
	}
	dt {
		color: var(--muted);
	}
	dd {
		margin: 0;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	dd a {
		color: var(--fg);
		text-decoration: none;
	}
	.card {
		font-size: 0.74rem;
	}
	dd a:hover {
		color: var(--gold-text);
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
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
	.chip:hover {
		color: var(--fg);
		border-color: var(--line-strong);
	}
	.chip.danger {
		color: var(--danger);
	}
	.ask {
		font-size: 0.78rem;
		color: var(--fg-2);
		flex: 1 1 100%;
	}
</style>
