<script lang="ts">
	import Prose from '#lib/Prose.svelte';
	import type { Message } from '#lib/api.ts';

	/** One turn in the conversation: the reader's gold-edged on the right, the character's on
	 * the left. Every character reply says which turn and model it is; the newest offers a
	 * reroll. A turn's actions are one of three things, by device: a pill on hover (a mouse), the
	 * footer's buttons or ⋯ (the newest reply), or a long press or right click that opens the
	 * turn's sheet (touch, and anywhere). */
	let {
		message,
		streaming = false,
		newest = false,
		onreroll,
		onmenu,
		onbranch,
		oncut,
		oncopy
	}: {
		message: Pick<Message, 'role' | 'text'> & Partial<Message>;
		streaming?: boolean;
		newest?: boolean;
		onreroll?: () => void;
		onmenu?: () => void;
		onbranch?: () => void;
		oncut?: () => void;
		oncopy?: () => void;
	} = $props();

	const mine = $derived(message.role === 'user');
	const actions = $derived(!streaming && !!(onbranch && oncut && oncopy));

	function shortModel(model: string | null | undefined): string | null {
		if (!model) return null;
		return model.split('/').pop() ?? model;
	}

	const turn = $derived(message.sequence ? `turn ${message.sequence}` : '');
	const model = $derived(shortModel(message.model));

	// A long press (or a right click) opens the turn's menu; a tap does nothing, so reading
	// is never interrupted.
	let timer: ReturnType<typeof setTimeout> | null = null;
	function press() {
		if (!onmenu || streaming) return;
		timer = setTimeout(() => {
			timer = null;
			onmenu?.();
		}, 450);
	}
	function release() {
		if (timer) clearTimeout(timer);
		timer = null;
	}
	function contextmenu(event: MouseEvent) {
		if (!onmenu || streaming) return;
		event.preventDefault();
		onmenu();
	}
</script>

<article
	class="msg"
	class:mine
	class:streaming
	onpointerdown={press}
	onpointerup={release}
	onpointercancel={release}
	onpointerleave={release}
	oncontextmenu={contextmenu}
>
	{#if message.text}
		<Prose text={message.text} />
	{:else if streaming}
		<span class="thinking muted">…</span>
	{/if}
	{#if actions}
		<div class="hover" role="toolbar" aria-label="This turn">
			<button type="button" onclick={onbranch}>Branch here</button>
			<button type="button" onclick={oncut}>Cut back to here</button>
			<button type="button" onclick={oncopy}>Copy</button>
		</div>
	{/if}
	{#if !mine && !streaming}
		<footer class="meta" class:older={!newest}>
			<span class="turn">{turn}<span class="model">{model ? ` · ${model}` : ''}</span></span>
			{#if newest && onreroll}
				<span class="grow"></span>
				<button type="button" class="reroll" onclick={onreroll}>↻ Reroll</button>
				{#if actions}
					<button type="button" class="text wide-only" onclick={onbranch}>Branch here</button>
					<button type="button" class="text wide-only" onclick={oncopy}>Copy</button>
				{/if}
				{#if onmenu}
					<button type="button" class="more" aria-label="More for this turn" onclick={onmenu}
						>⋯</button
					>
				{/if}
			{/if}
		</footer>
	{/if}
</article>

<style>
	.msg {
		--prose-size: 0.95rem;
		--prose-leading: 1.5;
		max-width: min(96%, 720px);
		padding: 9px 12px;
		border-radius: var(--r-l);
		background: var(--them);
		border: 1px solid var(--line);
		border-bottom-left-radius: 8px;
		align-self: flex-start;
		position: relative;
		user-select: text;
		-webkit-touch-callout: none;
	}
	.mine {
		background: var(--you);
		border-color: var(--you-line);
		border-bottom-left-radius: var(--r-l);
		border-bottom-right-radius: 8px;
		align-self: flex-end;
	}
	.streaming::after {
		content: '';
		display: inline-block;
		width: 8px;
		height: 1em;
		background: var(--gold);
		margin-left: 3px;
		vertical-align: -2px;
		border-radius: 2px;
		animation: blink 1s steps(2) infinite;
	}
	@keyframes blink {
		50% {
			opacity: 0;
		}
	}
	.thinking {
		font-size: 1.4rem;
		line-height: 1;
	}
	.meta {
		display: flex;
		gap: 6px;
		align-items: center;
		margin-top: 6px;
		font-size: 0.7rem;
		color: var(--muted);
	}
	.turn {
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		min-width: 0;
	}
	.grow {
		flex: 1;
	}
	.reroll,
	.text,
	.more {
		appearance: none;
		white-space: nowrap;
		font-weight: 600;
		font-size: 0.72rem;
	}
	.reroll {
		border: 1px solid var(--you-line);
		background: transparent;
		color: var(--gold-text);
		padding: 4px 12px;
		min-height: 32px;
		border-radius: var(--r-pill);
	}
	.text {
		border: 0;
		background: transparent;
		color: var(--fg-2);
		padding: 4px 10px;
		min-height: 32px;
		border-radius: var(--r-pill);
	}
	.text:hover {
		background: var(--surface-2);
	}
	.more {
		border: 0;
		background: var(--surface-2);
		color: var(--fg-2);
		font-size: 0.9rem;
		width: 32px;
		height: 32px;
		border-radius: 50%;
	}
	/* The hover pill: a mouse only, and only while the pointer or the keyboard is on the turn. */
	.hover {
		display: none;
	}
	@media (hover: hover) and (pointer: fine) {
		.hover {
			position: absolute;
			top: -14px;
			right: 10px;
			z-index: 2;
			display: flex;
			gap: 2px;
			padding: 2px;
			border-radius: var(--r-pill);
			background: var(--raised);
			border: 1px solid var(--line-strong);
			box-shadow: var(--shadow);
			opacity: 0;
			pointer-events: none;
			transition: opacity 0.12s ease;
		}
		.msg:hover .hover,
		.msg:focus-within .hover {
			opacity: 1;
			pointer-events: auto;
		}
		.hover button {
			appearance: none;
			border: 0;
			background: transparent;
			color: var(--fg-2);
			font-size: 0.72rem;
			font-weight: 600;
			padding: 4px 10px;
			border-radius: var(--r-pill);
			white-space: nowrap;
		}
		.hover button:hover {
			background: var(--gold-soft);
			color: var(--gold-text);
		}
	}
	/* A phone's footer is the newest reply's alone, and says only which turn; a wide window's is
	   under every reply and names the model, with Branch and Copy beside the reroll. */
	.meta.older,
	.model,
	.wide-only {
		display: none;
	}
	@media (min-width: 900px) {
		.meta.older {
			display: flex;
		}
		.model {
			display: inline;
		}
		.wide-only {
			display: inline-flex;
			align-items: center;
		}
		.more {
			display: none;
		}
	}
	/* The workspace's reading size. */
	@media (min-width: 1100px) {
		.msg {
			--prose-size: 0.98rem;
			--prose-leading: 1.55;
			max-width: min(92%, 680px);
			padding: 10px 14px;
		}
		.meta {
			font-size: 0.72rem;
			margin-top: 8px;
		}
	}
</style>
