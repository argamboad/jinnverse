<script lang="ts">
	import { goto } from '$app/navigation';
	import { api, ApiError, type Story } from '#lib/api.ts';
	import { rank } from '#lib/fuzzy.ts';
	import { Media, MOUSE } from '#lib/media.svelte.ts';
	import { stories } from '#lib/stories.svelte.ts';
	import { initial, when, whoLine } from '#lib/storyList.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	/** The stories as rows, best match of `query` first: one list for the Stories screen and the
	 * workspace's left rail (`rail`: tighter rows, the open story marked). On a touch screen a
	 * row dragged left shows Branch and Delete; with a mouse they show on hover instead. */
	let {
		query = '',
		current,
		rail = false
	}: { query?: string; current?: string; rail?: boolean } = $props();

	const mouse = new Media(MOUSE);
	/** The rail with a mouse has no swipe: its actions wait at the row's right end. */
	const hover = $derived(rail && mouse.current);

	// The donor's fuzzy filter over the story's name, best match first — the terminal's too, so
	// the same letters order the same stories in both clients (#135).
	const shown = $derived(rank(stories.list ?? [], query, (s) => s.name));

	let open = $state<string | null>(null); // the card whose actions are showing
	let confirming = $state<string | null>(null); // the card asked to confirm a delete
	let drag = $state<{ id: string; x: number; dx: number } | null>(null);

	function pointerdown(event: PointerEvent, id: string) {
		if (hover || (event.pointerType === 'mouse' && event.button !== 0)) return;
		drag = { id, x: event.clientX, dx: 0 };
	}
	function pointermove(event: PointerEvent) {
		if (!drag) return;
		drag.dx = event.clientX - drag.x;
	}
	function pointerup(event: PointerEvent, id: string) {
		if (!drag || drag.id !== id) return;
		const dx = event.clientX - drag.x;
		if (dx < -50) open = id;
		else if (dx > 30) open = null;
		else if (Math.abs(dx) < 8 && open === id) open = null;
		drag = null;
	}
	function offset(id: string): string {
		if (hover) return '0px';
		if (drag && drag.id === id && drag.dx < 0) return `${Math.max(drag.dx, -140)}px`;
		return open === id ? '-140px' : '0px';
	}

	async function branch(story: Story) {
		try {
			const full = await api.story(story.id);
			const last = full.messages.at(-1);
			if (!last) {
				toasts.show('info', 'Nothing to branch yet', 'The story has no turns.');
				return;
			}
			const copy = await api.branch(story.id, last.id);
			stories.touch(copy);
			open = null;
			toasts.show('ok', `Branched as “${copy.name}”`, 'The original is untouched.');
			await goto(`/story/${copy.id}`);
		} catch (error) {
			toasts.show('danger', 'Could not branch', error instanceof Error ? error.message : undefined);
		}
	}

	async function remove(story: Story) {
		try {
			await api.deleteStory(story.id);
			stories.remove(story.id);
			toasts.show('ok', `Deleted “${story.name}”`, 'Its rows stay until you purge it.');
			if (story.id === current) await goto('/');
		} catch (error) {
			toasts.show(
				'danger',
				'Could not delete',
				error instanceof ApiError ? error.message : undefined
			);
		} finally {
			confirming = null;
			open = null;
		}
	}
</script>

{#if stories.problem}
	<p class="problem">
		{stories.problem}
		<button class="btn ghost" type="button" onclick={() => stories.refresh()}>Try again</button>
	</p>
{:else if stories.list === null}
	<p class="muted center">Reading your stories…</p>
{:else if shown.length === 0}
	<div class="empty">
		{#if query}
			<p class="muted">Nothing matches “{query}”.</p>
		{:else}
			<p class="muted">No stories yet.</p>
			{#if !rail}<a class="btn primary" href="/new">Start one</a>{/if}
		{/if}
	</div>
{:else}
	{#each shown as story (story.id)}
		{@const reachable = hover || open === story.id}
		<div class="row" class:rail class:current={story.id === current}>
			<div class="actions" aria-hidden={!reachable}>
				<button
					type="button"
					class="act branch"
					onclick={() => branch(story)}
					tabindex={reachable ? 0 : -1}>Branch</button
				>
				<button
					type="button"
					class="act delete"
					onclick={() => (confirming = story.id)}
					tabindex={reachable ? 0 : -1}>Delete</button
				>
			</div>
			<a
				class="story"
				href="/story/{story.id}"
				aria-current={story.id === current ? 'page' : undefined}
				style:transform="translateX({offset(story.id)})"
				onpointerdown={(e) => pointerdown(e, story.id)}
				onpointermove={pointermove}
				onpointerup={(e) => pointerup(e, story.id)}
				onpointercancel={() => (drag = null)}
				onclick={(e) => {
					if (open === story.id || (drag && Math.abs(drag.dx) > 8)) e.preventDefault();
				}}
				draggable="false"
			>
				<div class="who">{initial(story)}</div>
				<div class="text">
					<div class="name">
						<span>{story.name}</span>
					</div>
					{#if !rail}<div class="line">{whoLine(story)}</div>{/if}
					{#if story.turns > 0 && story.last_message_preview}
						<div class="preview prose">{story.last_message_preview}</div>
					{:else if rail}
						<div class="preview muted">Nothing said yet</div>
					{/if}
				</div>
				<div class="when">{when(story)}</div>
			</a>
			{#if confirming === story.id}
				<div class="confirm" role="alertdialog" aria-label="Delete this story?">
					<span>Delete “{story.name}”? It is hidden, not erased.</span>
					<button type="button" class="btn ghost" onclick={() => (confirming = null)}>Keep</button>
					<button type="button" class="btn danger" onclick={() => remove(story)}>Delete</button>
				</div>
			{/if}
		</div>
	{/each}
{/if}

<style>
	.row {
		position: relative;
		border-radius: var(--r-m);
		overflow: hidden;
	}
	.actions {
		position: absolute;
		inset: 0 0 0 auto;
		width: 140px;
		display: flex;
	}
	.act {
		flex: 1;
		border: 0;
		font-weight: 600;
		font-size: 0.8rem;
		color: #fff;
	}
	.act.branch {
		background: var(--gold-2);
		color: var(--gold-ink);
	}
	.act.delete {
		background: var(--danger);
	}
	.story {
		position: relative;
		display: grid;
		grid-template-columns: 44px 1fr auto;
		gap: 10px;
		padding: 10px;
		border-radius: var(--r-m);
		background: var(--surface);
		border: 1px solid var(--line);
		text-decoration: none;
		color: inherit;
		transition: transform 0.18s ease;
		touch-action: pan-y;
		user-select: none;
	}
	.story:active {
		background: var(--surface-2);
	}
	.who {
		width: 44px;
		height: 44px;
		border-radius: 12px;
		background: var(--surface-2);
		display: grid;
		place-items: center;
		font-family: var(--font-prose);
		font-size: 1.25rem;
		color: var(--gold-text);
	}
	.text {
		min-width: 0;
		display: grid;
		gap: 2px;
	}
	.name {
		font-weight: 600;
		display: flex;
		gap: 8px;
		align-items: center;
		min-width: 0;
	}
	.name > span:first-child {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.line {
		font-size: 0.74rem;
		color: var(--muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.preview {
		color: var(--fg-2);
		font-size: 0.88rem;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		line-height: 1.4;
	}
	.when {
		font-size: 0.72rem;
		color: var(--muted);
		padding-top: 2px;
		white-space: nowrap;
	}
	.confirm {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		align-items: center;
		padding: 10px 12px;
		background: var(--surface-2);
		border-top: 1px solid var(--line);
		font-size: 0.88rem;
		color: var(--fg-2);
	}
	.confirm span {
		flex: 1 1 100%;
	}
	.btn.danger {
		background: var(--danger);
		color: #fff;
	}
	.problem {
		display: grid;
		gap: 10px;
		justify-items: start;
		color: var(--danger);
		padding: 16px 4px;
	}
	.center {
		text-align: center;
		padding: 32px 0;
	}
	.empty {
		display: grid;
		gap: 14px;
		justify-items: center;
		padding: 48px 16px;
		text-align: center;
	}

	/* The rail: tighter rows, one line of preview, the open story outlined. */
	.rail {
		border-radius: 12px;
	}
	.rail .story {
		grid-template-columns: 36px 1fr auto;
		padding: 10px;
		border-radius: 12px;
		background: transparent;
		border-color: transparent;
	}
	.rail .story:hover {
		background: var(--surface);
	}
	.rail.current .story {
		background: var(--surface);
		border-color: var(--you-line);
	}
	.rail .who {
		width: 36px;
		height: 36px;
		border-radius: 10px;
	}
	.rail.current .who {
		background: var(--gold-soft);
	}
	.rail .text {
		gap: 1px;
	}
	.rail .name {
		font-size: 0.92rem;
	}
	.rail .preview {
		font-size: 0.8rem;
		display: block;
		white-space: nowrap;
		text-overflow: ellipsis;
		line-height: 1.5;
	}
	.rail .when {
		font-size: 0.7rem;
	}
	/* With a mouse the actions wait at the row's right end until the row is under it. */
	@media (hover: hover) and (pointer: fine) {
		.rail .actions {
			inset: 50% 8px auto auto;
			transform: translateY(-50%);
			width: auto;
			gap: 4px;
			z-index: 2;
			opacity: 0;
			pointer-events: none;
			transition: opacity 0.12s ease;
		}
		.rail:hover .actions,
		.rail:focus-within .actions {
			opacity: 1;
			pointer-events: auto;
		}
		.rail .act {
			flex: none;
			padding: 4px 10px;
			border-radius: var(--r-pill);
			font-size: 0.72rem;
		}
		.rail:hover .when,
		.rail:focus-within .when {
			opacity: 0;
		}
	}
</style>
