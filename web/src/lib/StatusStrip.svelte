<script lang="ts">
	import type { Status } from '#lib/api.ts';
	import { inScene, sceneLines } from '#lib/status.ts';

	/** Under the app bar: the scene's lines (the day, the place) and who is in it. A tap opens
	 * the Status tab, where any of it can be corrected. Nothing shows until a reply has written a
	 * line, or for a story with no field on. */
	let { status, newest, onopen }: { status: Status | null; newest: number; onopen: () => void } =
		$props();

	const lines = $derived(status ? sceneLines(status) : []);
	const people = $derived(status ? inScene(status, newest) : []);
	const shown = $derived(status?.fields.some((f) => f.enabled) && (lines.length || people.length));
</script>

{#if shown}
	<button type="button" class="strip" onclick={onopen} aria-label="Status: open the Status tab">
		{#if lines.length > 0}
			<span class="scene">
				{#each lines as line (line.field.key)}
					<span class="item" title={line.field.label}>
						{#if line.field.icon}<i aria-hidden="true">{line.field.icon}</i>{:else}<em
								>{line.field.label}:</em
							>{/if}
						{line.value}
					</span>
				{/each}
			</span>
		{/if}
		{#if people.length > 0}
			<span class="people">
				{#each people as person (person.who)}
					<span class="chip" class:pinned={person.pinned}>{person.who}</span>
				{/each}
			</span>
		{/if}
	</button>
{/if}

<style>
	.strip {
		display: grid;
		gap: 6px;
		text-align: left;
		width: calc(100% - 20px);
		max-width: var(--frame, 860px);
		margin: 8px auto 0;
		padding: 8px 12px;
		border-radius: var(--r-s);
		background: var(--surface);
		border: 1px solid var(--line);
		color: var(--fg-2);
		font-size: 0.8rem;
		min-height: 44px;
	}
	.scene {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 14px;
	}
	.item i {
		font-style: normal;
		margin-right: 4px;
	}
	.item em {
		font-style: normal;
		color: var(--muted);
		margin-right: 4px;
	}
	.people {
		display: flex;
		gap: 6px;
		overflow-x: auto;
		scrollbar-width: none;
	}
	.chip {
		flex: none;
		padding: 2px 10px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--line);
		font-size: 0.75rem;
		color: var(--fg);
	}
	.chip.pinned {
		background: var(--gold-soft);
	}
</style>
