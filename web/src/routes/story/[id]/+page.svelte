<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount, tick, untrack } from 'svelte';
	import AppBar from '#lib/AppBar.svelte';
	import Composer from '#lib/Composer.svelte';
	import MessageView from '#lib/MessageView.svelte';
	import MeterStrip from '#lib/MeterStrip.svelte';
	import RerollSheet from '#lib/RerollSheet.svelte';
	import Sheet from '#lib/Sheet.svelte';
	import StatusStrip from '#lib/StatusStrip.svelte';
	import StoriesRail from '#lib/StoriesRail.svelte';
	import StoryHead from '#lib/StoryHead.svelte';
	import StoryRail from '#lib/StoryRail.svelte';
	import StorySheet from '#lib/StorySheet.svelte';
	import {
		api,
		ApiError,
		Unreachable,
		type Command,
		type Done,
		type EntryFull,
		type Message,
		type StoryWithMessages
	} from '#lib/api.ts';
	import { readEmoji } from '#lib/emoji.ts';
	import { Extras } from '#lib/extras.svelte.ts';
	import { Media, WIDE } from '#lib/media.svelte.ts';
	import { money } from '#lib/money.ts';
	import { expandEmoji } from '#lib/shortcodes.ts';
	import { stories } from '#lib/stories.svelte.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	const id = $derived(page.params.id ?? '');

	let story = $state<StoryWithMessages | null>(null);
	let problem = $state<string | null>(null);
	let commands = $state<Command[]>([]);
	let snippets = $state<EntryFull[]>([]);
	/** The reader's message as sent, before the API confirms it. */
	let pendingSent = $state<string | null>(null);
	/** The reply as it streams in. */
	let pendingReply = $state<string | null>(null);
	/** The newest reply, hidden while a reroll writes its replacement. */
	let replacing = $state<string | null>(null);
	/** Answers shown once and kept nowhere: `/ask`, `/recap`, a `/tracker` set. */
	let notes = $state<{ id: number; title: string; text: string }[]>([]);
	let rerollOpen = $state(false);
	/** The turn the sheet is about, and whether it is showing. */
	let menuFor = $state<Message | null>(null);
	let turnOpen = $state(false);
	/** Whether the reader has opened a turn's sheet once: until then a line says how. */
	let hintSeen = $state(true);
	/** The story's own sheet, opened from the title. */
	let storyOpen = $state(false);
	let extras = $state<Extras | null>(null);
	/** The Dials sheet (a phone, or a window narrower than the workspace) and the tab it is on. */
	let panelOpen = $state(false);
	let panelTab = $state<'dials' | 'meters' | 'status' | 'prompt'>('dials');
	let cutConfirm = $state(false);
	/** From 1100 px the story sits in a workspace: the stories rail, the conversation, the column. */
	const wideWindow = new Media(WIDE);
	const wide = $derived(wideWindow.current);
	let head: StoryHead | undefined = $state();
	let composer: Composer | undefined = $state();
	let scroller: HTMLElement | undefined = $state();
	let noteId = 1;

	const busy = $derived(pendingReply !== null);
	const visible = $derived((story?.messages ?? []).filter((m) => m.id !== replacing));
	const newestReply = $derived.by(() => {
		const last = visible.at(-1);
		return last && last.role === 'assistant' ? last : null;
	});
	const turns = $derived(visible.filter((m) => m.role === 'user').length);
	const sub = $derived.by(() => {
		if (!story) return '';
		const parts = [story.character_name, story.persona_name ?? 'no persona', `turn ${turns}`];
		return parts.join(' · ');
	});

	const HINT_KEY = 'lustjinn-turn-hint';

	function openTurn(message: Message) {
		menuFor = message;
		cutConfirm = false;
		turnOpen = true;
		hintSeen = true;
		try {
			localStorage.setItem(HINT_KEY, '1');
		} catch {
			/* a private window: the hint shows again next time */
		}
	}

	/** The hover pill's "Cut back to here": the turn's sheet, already on the confirmation. */
	function askCut(message: Message) {
		menuFor = message;
		cutConfirm = true;
		turnOpen = true;
	}

	/** The Dials sheet on a phone; on a wide window the column is already there, so only its tab changes. */
	function openPanel(tab: typeof panelTab = 'dials') {
		panelTab = tab;
		if (!wide) panelOpen = true;
	}

	// Widening the window past the workspace's breakpoint hands the sheets' work to the column.
	$effect(() => {
		if (wide) {
			panelOpen = false;
			storyOpen = false;
		}
	});

	onMount(() => {
		try {
			hintSeen = localStorage.getItem(HINT_KEY) === '1';
		} catch {
			hintSeen = false;
		}
	});

	// The workspace's rail changes the story under this page without leaving it, so the page
	// reads the story again whenever the id changes, not only when it opens.
	let shownId = '';
	$effect(() => {
		const target = id;
		if (target && target !== shownId) {
			shownId = target;
			untrack(() => void openStory(target));
		}
	});

	async function openStory(target: string) {
		story = null;
		problem = null;
		extras = null;
		notes = [];
		pendingSent = null;
		pendingReply = null;
		replacing = null;
		turnOpen = false;
		storyOpen = false;
		panelOpen = false;
		// `?tab=meters` (and the others) open the sheet on that tab.
		const tab = page.url.searchParams.get('tab');
		if (tab === 'dials' || tab === 'meters' || tab === 'status' || tab === 'prompt') openPanel(tab);
		try {
			const [found, known] = await Promise.all([api.story(target), api.commands()]);
			if (target !== id) return; // another story was opened while this one was read
			story = found;
			commands = known;
			void readEmoji(api.emoji); // once per session; until then nothing expands
			if (snippets.length === 0) {
				api
					.snippets()
					.then((list) => (snippets = list))
					.catch(() => undefined);
			}
			extras = new Extras(target);
			void extras.load();
			await scrollToEnd(false);
		} catch (error) {
			if (target === id)
				problem = error instanceof Error ? error.message : 'The story could not be read.';
		}
	}

	async function scrollToEnd(smooth = true) {
		await tick();
		scroller?.scrollTo({ top: scroller.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
	}

	function touchStoryList() {
		if (!story) return;
		const last = story.messages.at(-1);
		stories.touch({
			...story,
			last_message_at: last?.sent_at ?? story.last_message_at,
			last_message_preview: last?.text.slice(0, 200) ?? story.last_message_preview,
			turns: story.messages.filter((m) => m.role === 'user').length
		});
	}

	function note(title: string, text: string) {
		notes = [...notes, { id: noteId++, title, text }];
		void scrollToEnd();
	}

	/** Runs one streamed call and folds what it ends with into the story. */
	async function run(call: (onDelta: (t: string) => void) => Promise<Done>) {
		if (!story) return;
		const started = id;
		pendingReply = '';
		try {
			const done = await call((piece) => {
				if (id === started) pendingReply = (pendingReply ?? '') + piece;
				void scrollToEnd();
			});
			// The reader may have opened another story from the rail while this one was answering.
			if (id === started) finish(done);
		} catch (error) {
			if (error instanceof ApiError) toasts.show('danger', 'Refused', error.message, 8000);
			else if (error instanceof Unreachable)
				toasts.show('danger', 'Lost the server', error.message);
			else toasts.show('danger', 'Something went wrong');
			await reload();
		} finally {
			pendingReply = null;
			pendingSent = null;
			replacing = null;
		}
	}

	function finish(done: Done) {
		if (!story) return;
		switch (done.kind) {
			case 'turn': {
				const kept = story.messages.filter((m) => m.id !== replacing);
				const added = [done.sent, done.reply].filter((m): m is Message => m !== null);
				story.messages = [...kept, ...added.filter((a) => !kept.some((k) => k.id === a.id))];
				if (done.replayed)
					toasts.show(
						'info',
						'Already answered',
						'That message had been sent before; here is its reply.'
					);
				touchStoryList();
				void extras?.refresh(); // the meters may have moved; the audit has a new line
				break;
			}
			case 'aside':
				note(`You asked: ${done.aside.question}`, done.aside.answer);
				break;
			case 'said':
				note('', done.text);
				void extras?.refresh(); // a /tracker or /status set changed what the strip shows
				break;
			case 'error':
				toasts.show('danger', 'The model did not answer', done.detail, 10000);
				if (done.sent && !story.messages.some((m) => m.id === done.sent?.id)) {
					story.messages = [...story.messages, done.sent];
				}
				break;
		}
		void scrollToEnd();
	}

	async function reload() {
		try {
			story = await api.story(id);
		} catch {
			/* the next action reloads again */
		}
	}

	function send(typed: string) {
		// Emoji shortcodes expand here; a bare `:name` is a snippet trigger the API expands.
		const text = expandEmoji(typed);
		pendingSent = text;
		void scrollToEnd();
		void run((onDelta) => api.send(id, text, onDelta));
	}

	function carryOn() {
		void run((onDelta) => api.carryOn(id, onDelta));
	}

	function reroll(reason: string, instructions: string | null) {
		if (!newestReply) return;
		replacing = newestReply.id;
		void run((onDelta) => api.reroll(id, onDelta, { reason, instructions }));
	}

	async function branchFrom(message: Message) {
		if (!story) return;
		turnOpen = false;
		try {
			const copy = await api.branch(id, message.id);
			stories.touch(copy);
			toasts.show(
				'ok',
				`Branched as “${copy.name}”`,
				`From turn ${message.sequence}. The original is untouched.`
			);
			await goto(`/story/${copy.id}`);
			story = copy;
			await scrollToEnd(false);
		} catch (error) {
			toasts.show('danger', 'Could not branch', error instanceof Error ? error.message : undefined);
		}
	}

	async function cutFrom(message: Message) {
		if (!story) return;
		try {
			const result = await api.deleteFrom(id, message.id);
			story = result.story;
			toasts.show(
				'ok',
				`Cut ${result.hidden} ${result.hidden === 1 ? 'turn' : 'turns'}`,
				'They are hidden, and the memory of them went with them.'
			);
			touchStoryList();
			void extras?.refresh(); // the status block is read again from what remains
		} catch (error) {
			toasts.show('danger', 'Could not cut', error instanceof Error ? error.message : undefined);
		} finally {
			turnOpen = false;
			cutConfirm = false;
		}
	}

	async function copyText(message: Message) {
		turnOpen = false;
		try {
			await navigator.clipboard.writeText(message.text);
			toasts.show('ok', 'Copied');
		} catch {
			toasts.show('info', 'Select the text to copy it');
		}
	}

	/** The name changes at once; if the API refuses, it goes back and a toast says why. */
	async function rename(name: string) {
		if (!story) return;
		const before = story.name;
		story.name = name;
		try {
			const renamed = await api.renameStory(id, name);
			story.name = renamed.name;
			stories.touch({ ...story, ...renamed });
		} catch (error) {
			story.name = before;
			toasts.show('danger', 'Could not rename', error instanceof Error ? error.message : undefined);
		}
	}

	async function deleteStory() {
		if (!story) return;
		try {
			await api.deleteStory(id);
			stories.remove(id);
			toasts.show('ok', `Deleted “${story.name}”`);
			await goto('/');
		} catch (error) {
			toasts.show('danger', 'Could not delete', error instanceof Error ? error.message : undefined);
		}
	}

	const cutCount = $derived(
		menuFor && story ? visible.filter((m) => m.sequence >= menuFor!.sequence).length : 0
	);
</script>

<div class={wide ? 'workspace' : 'screen'}>
	{#if wide}<StoriesRail current={id} />{/if}
	<div class="pane" class:wide>
		{#if wide}
			<header class="bar">
				<button type="button" class="title" onclick={() => head?.focus()}>
					<h1>{story?.name ?? 'Story'}</h1>
					<span class="sub">{sub}</span>
				</button>
				<span class="grow"></span>
				{#if extras?.spend}<span class="cost mono">{money(extras.spend.cost)} this story</span>{/if}
			</header>
		{:else}
			<AppBar
				title={story?.name ?? 'Story'}
				{sub}
				back="/"
				ontitle={story ? () => (storyOpen = true) : undefined}
				titleOpen={storyOpen}
			>
				{#snippet actions()}
					<button
						class="dials"
						class:on={panelOpen}
						type="button"
						aria-expanded={panelOpen}
						onclick={() => openPanel()}><span aria-hidden="true">◐</span>Dials</button
					>
				{/snippet}
			</AppBar>
		{/if}

		{#if extras}
			<StatusStrip
				status={extras.status}
				newest={visible.at(-1)?.sequence ?? 0}
				onopen={() => openPanel('status')}
			/>
		{/if}

		<main class="convo" bind:this={scroller}>
			{#if problem}
				<p class="problem">{problem}</p>
			{:else if !story}
				<p class="muted center">Opening the story…</p>
			{:else}
				{#if story.messages.length === 0 && !pendingSent}
					<p class="muted center">
						Nothing has been said yet. Write the first turn, or carry on to let {story.character_name}
						begin.
					</p>
				{/if}
				{#each visible as message (message.id)}
					<MessageView
						{message}
						newest={newestReply?.id === message.id && !busy}
						onreroll={() => (rerollOpen = true)}
						onmenu={() => openTurn(message)}
						onbranch={() => branchFrom(message)}
						oncut={() => askCut(message)}
						oncopy={() => copyText(message)}
					/>
				{/each}
				{#each notes as n (n.id)}
					<aside class="note">
						{#if n.title}<b>{n.title}</b>{/if}
						<p class="prose">{n.text}</p>
						<footer>
							<span class="muted">shown once, not stored</span>
							<button
								type="button"
								class="link"
								onclick={() => (notes = notes.filter((x) => x.id !== n.id))}>Dismiss</button
							>
						</footer>
					</aside>
				{/each}
				{#if pendingSent !== null}
					<MessageView message={{ role: 'user', text: pendingSent }} />
				{/if}
				{#if pendingReply !== null}
					<MessageView message={{ role: 'assistant', text: pendingReply }} streaming />
				{/if}
				{#if !hintSeen && visible.length > 0 && !busy}
					<p class="hint">Hold any turn to branch, cut or copy</p>
				{/if}
			{/if}
		</main>

		{#if extras}
			<MeterStrip trackers={extras.trackers} onopen={() => openPanel('meters')} />
		{/if}
		<Composer
			bind:this={composer}
			{commands}
			{snippets}
			{busy}
			split={wide}
			onsend={send}
			oncarryon={carryOn}
		/>
	</div>
	{#if wide}
		<aside class="column" aria-label="Dials">
			{#if story}
				<StoryHead
					bind:this={head}
					{story}
					canBranch={newestReply !== null}
					onrename={rename}
					onbranch={() => newestReply && branchFrom(newestReply)}
					ondelete={deleteStory}
				/>
			{/if}
			<div class="railbody">
				{#if extras}<StoryRail {extras} bind:section={panelTab} compact />{/if}
			</div>
		</aside>
	{/if}
</div>

<RerollSheet bind:open={rerollOpen} onreroll={reroll} />

<Sheet bind:open={panelOpen} title="Dials" hint="saved as you touch them" max="88%">
	{#if extras}
		<StoryRail {extras} bind:section={panelTab} />
	{/if}
</Sheet>

<Sheet
	bind:open={turnOpen}
	title="Turn {menuFor?.sequence ?? ''}"
	hint={menuFor?.role === 'user' ? 'yours' : story?.character_name}
>
	{#if menuFor}
		{#if !cutConfirm}
			<div class="menu">
				<button type="button" class="btn" onclick={() => menuFor && branchFrom(menuFor)}
					>Branch from here</button
				>
				<button type="button" class="btn" onclick={() => (cutConfirm = true)}
					>Cut the story back to here</button
				>
				<button type="button" class="btn" onclick={() => menuFor && copyText(menuFor)}
					>Copy the text</button
				>
				<button type="button" class="btn ghost" onclick={() => (turnOpen = false)}>Close</button>
			</div>
		{:else}
			<p class="muted">
				This hides {cutCount}
				{cutCount === 1 ? 'turn' : 'turns'} from turn {menuFor.sequence} on, and the memory built from
				them. The rows stay.
			</p>
			<div class="menu">
				<button type="button" class="btn danger" onclick={() => menuFor && cutFrom(menuFor)}
					>Cut {cutCount} {cutCount === 1 ? 'turn' : 'turns'}</button
				>
				<button type="button" class="btn ghost" onclick={() => (cutConfirm = false)}
					>Keep them</button
				>
			</div>
		{/if}
	{/if}
</Sheet>

<StorySheet
	bind:open={storyOpen}
	{story}
	spend={extras?.spend ?? null}
	canBranch={newestReply !== null}
	onrename={rename}
	onbranch={() => {
		storyOpen = false;
		if (newestReply) void branchFrom(newestReply);
	}}
	ondelete={deleteStory}
/>

<style>
	.screen {
		height: 100%;
		display: flex;
		flex-direction: column;
	}
	.pane {
		flex: 1;
		min-height: 0;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}
	/* The workspace, 1100 px and up: no centred frame, three panes the height of the window. */
	.workspace {
		height: 100%;
		display: grid;
		grid-template-columns: 300px minmax(0, 1fr) 340px;
	}
	.pane.wide {
		--strip-x: 24px;
	}
	.pane.wide .convo {
		padding: 16px 24px 10px;
		gap: 10px;
	}
	.bar {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 0 20px;
		min-height: 62px;
		border-bottom: 1px solid var(--line);
	}
	.bar .title {
		appearance: none;
		border: 0;
		background: transparent;
		color: inherit;
		text-align: left;
		min-width: 0;
		display: grid;
		padding: 0;
	}
	.bar h1 {
		font-size: 1.05rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.bar .sub {
		font-size: 0.74rem;
		color: var(--muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.bar .grow {
		flex: 1;
	}
	.bar .cost {
		font-size: 0.74rem;
		color: var(--muted);
	}
	.column {
		display: flex;
		flex-direction: column;
		min-height: 0;
		min-width: 0;
		background: var(--bg-2);
		border-left: 1px solid var(--line);
	}
	.railbody {
		flex: 1;
		min-height: 0;
	}
	.convo {
		flex: 1;
		min-height: 0; /* a flex child shrinks only when told to; without this nothing scrolls */
		overflow-y: auto;
		padding: 8px 10px 10px;
		display: flex;
		flex-direction: column;
		gap: 8px;
		overscroll-behavior: contain;
		-webkit-overflow-scrolling: touch;
	}
	/* Short conversations sit at the bottom; long ones scroll. Never `align-content: end` here:
	   content taller than the box then overflows upward, where no browser can scroll. */
	.convo > :first-child {
		margin-top: auto;
	}
	.center {
		text-align: center;
		padding: 32px 16px;
	}
	.hint {
		align-self: center;
		font-size: 0.7rem;
		color: var(--muted);
		padding-top: 2px;
	}
	/* A mouse has the hover pill; the line is for a finger. */
	@media (hover: hover) and (pointer: fine) {
		.hint {
			display: none;
		}
	}
	.problem {
		color: var(--danger);
		padding: 16px;
	}
	.note {
		align-self: center;
		width: min(100%, 560px);
		padding: 12px 14px;
		border-radius: var(--r-m);
		background: var(--surface);
		border: 1px dashed var(--line-strong);
		display: grid;
		gap: 6px;
		font-size: 0.92rem;
	}
	.note b {
		font-size: 0.85rem;
		color: var(--gold-text);
	}
	.note p {
		white-space: pre-wrap;
		color: var(--fg-2);
	}
	.note footer {
		display: flex;
		justify-content: space-between;
		font-size: 0.72rem;
	}
	.dials {
		appearance: none;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 36px;
		padding: 0 12px 0 10px;
		border-radius: var(--r-pill);
		border: 1px solid var(--line-strong);
		background: transparent;
		color: var(--gold-text);
		font-weight: 600;
		font-size: 0.82rem;
	}
	.dials span {
		font-size: 1rem;
		line-height: 1;
	}
	.dials.on {
		background: var(--gold-soft);
		border-color: var(--gold);
	}
	.link {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--gold-text);
		font-weight: 600;
		font-size: 0.72rem;
		min-height: 32px;
	}
	.menu {
		display: grid;
		gap: 8px;
	}
	.btn.danger {
		background: var(--danger);
		color: #fff;
	}
</style>
