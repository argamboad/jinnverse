<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import AppBar from '#lib/AppBar.svelte';
	import LibraryRail from '#lib/LibraryRail.svelte';
	import Sheet from '#lib/Sheet.svelte';
	import {
		api,
		type PersonaPreview,
		type Picks,
		type Piece,
		type Slot,
		type Voice
	} from '#lib/api.ts';
	import { pieceBlurb } from '#lib/library.ts';
	import { Media } from '#lib/media.svelte.ts';
	import {
		VOICES,
		builderLine,
		groupSlots,
		hasText,
		isNeeded,
		keeping,
		missingSentence,
		randomFor,
		toggled,
		type SlotGroup
	} from '#lib/personaBuilder.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	/** Building a persona from pieces: a checklist of slots, each opening its pool in a sheet,
	 * and the persona as the server joins it, one tap away. */
	/** Where to go once the persona is made: back to the new-story form when it came from there. */
	const then = $derived(page.url.searchParams.get('then'));
	const wide = new Media('(min-width: 900px)');

	let voice = $state<Voice>('he');
	let slots = $state<Slot[]>([]);
	let pool = $state<Piece[]>([]);
	let picks = $state<Picks>({});
	let loaded = $state(false);
	let view = $state<'slots' | 'read'>('slots');

	/** The row whose pool is open in the slot sheet. */
	let group = $state<SlotGroup | null>(null);
	let groupOpen = $state(false);

	let preview = $state<PersonaPreview | null>(null);
	let previewError = $state<string | null>(null);
	let libraryName = $state('');
	let renaming = $state(false);
	let busy = $state(false);

	let sheetOpen = $state(false);
	let sheetSlot = $state<Slot | null>(null);
	let pieceName = $state('');
	let pieceText = $state('');
	let fullName = $state('');
	let shortName = $state('');
	let saving = $state(false);

	const groups = $derived(groupSlots(slots));
	const shelvedAs = $derived(libraryName.trim() || preview?.name || null);
	const sheetReady = $derived(
		sheetSlot?.key === 'name'
			? fullName.trim().length > 0 && shortName.trim().length > 0
			: pieceName.trim().length > 0 && pieceText.trim().length > 0
	);

	/** The pick survives a trip to the piece editor and back: kept for this tab only. */
	const REMEMBERED = 'lustjinn-builder';

	function remember(pick: Picks, as: Voice) {
		try {
			sessionStorage.setItem(REMEMBERED, JSON.stringify({ voice: as, picks: pick }));
		} catch {
			/* a convenience only */
		}
	}

	function forget() {
		try {
			sessionStorage.removeItem(REMEMBERED);
		} catch {
			/* a convenience only */
		}
	}

	onMount(async () => {
		try {
			const kept = JSON.parse(sessionStorage.getItem(REMEMBERED) ?? 'null') as {
				voice: Voice;
				picks: Picks;
			} | null;
			if (kept) {
				voice = kept.voice;
				picks = kept.picks;
			}
		} catch {
			/* a convenience only */
		}
		try {
			[slots, pool] = await Promise.all([api.pieceSlots(), api.pieces(voice)]);
			// A piece deleted meanwhile, or written in another voice, is put back.
			picks = keeping(picks, new Set(pool.map((p) => p.id)));
		} catch (error) {
			toasts.show(
				'danger',
				'Could not read the pieces',
				error instanceof Error ? error.message : undefined
			);
		} finally {
			loaded = true;
		}
	});

	// The preview is the server's own join, asked again a moment after the pick stops changing; an
	// answer to an earlier pick is dropped when a later one has been asked for.
	let asked = 0;
	$effect(() => {
		const now = $state.snapshot(picks);
		const as = voice;
		const mine = ++asked;
		remember(now, as);
		if (!hasText(now)) {
			preview = null;
			previewError = null;
			return;
		}
		const timer = setTimeout(async () => {
			try {
				const found = await api.previewPersona(as, now);
				if (mine === asked) {
					preview = found;
					previewError = null;
				}
			} catch (error) {
				if (mine === asked) {
					preview = null;
					previewError = error instanceof Error ? error.message : 'Could not join the pieces.';
				}
			}
		}, 150);
		return () => clearTimeout(timer);
	});

	function piecesOf(slot: string): Piece[] {
		return pool.filter((p) => p.slot === slot);
	}

	function pickedIn(g: SlotGroup): Piece[] {
		return g.slots.flatMap((s) =>
			(picks[s.key] ?? [])
				.map((id) => pool.find((p) => p.id === id))
				.filter((p): p is Piece => p !== undefined)
		);
	}

	function neededIn(g: SlotGroup): boolean {
		return g.slots.some((s) => isNeeded(s.key));
	}

	async function changeVoice(next: Voice) {
		if (next === voice) return;
		voice = next;
		try {
			pool = await api.pieces(next);
			picks = keeping(picks, new Set(pool.map((p) => p.id)));
		} catch (error) {
			toasts.show(
				'danger',
				'Could not read the pieces',
				error instanceof Error ? error.message : undefined
			);
		}
	}

	function toggle(slot: string, id: string) {
		picks = toggled(picks, slot, id);
	}

	/** A piece at random for each slot of the row; says so when the row has nothing to pick. */
	function randomRow(g: SlotGroup) {
		const next = { ...picks };
		let any = false;
		for (const slot of g.slots) {
			const id = randomFor(
				piecesOf(slot.key).map((p) => p.id),
				Math.random()
			);
			if (id !== null) {
				next[slot.key] = [id];
				any = true;
			}
		}
		if (!any) {
			toasts.show('info', `No ${g.label.toLowerCase()} piece yet`, 'Write the first one.');
			return;
		}
		picks = next;
	}

	function randomAll() {
		const next = { ...picks };
		for (const slot of slots) {
			if (next[slot.key]?.length) continue;
			const id = randomFor(
				piecesOf(slot.key).map((p) => p.id),
				Math.random()
			);
			if (id !== null) next[slot.key] = [id];
		}
		picks = next;
	}

	function openRow(g: SlotGroup) {
		group = g;
		groupOpen = true;
	}

	function writeNew(slot: Slot) {
		groupOpen = false;
		sheetSlot = slot;
		pieceName = '';
		pieceText = '';
		fullName = '';
		shortName = '';
		sheetOpen = true;
	}

	function insert(token: string) {
		pieceText = pieceText ? `${pieceText} ${token}` : token;
	}

	async function savePiece(event: SubmitEvent) {
		event.preventDefault();
		const slot = sheetSlot;
		if (!slot || !sheetReady || saving) return;
		saving = true;
		try {
			const made =
				slot.key === 'name'
					? await api.createPiece({
							slot: 'name',
							voice,
							name: fullName.trim(),
							text: fullName.trim(),
							short: shortName.trim()
						})
					: await api.createPiece({
							slot: slot.key,
							voice,
							name: pieceName.trim(),
							text: pieceText.trim()
						});
			pool = [...pool, made];
			picks = toggled(picks, slot.key, made.id);
			sheetOpen = false;
			groupOpen = group !== null; // back to the row's pool, with the new piece picked
			toasts.show('ok', `${made.name} is in the pool`, 'It is picked, and stays for next time.');
		} catch (error) {
			toasts.show(
				'danger',
				'Piece not saved',
				error instanceof Error ? error.message : undefined,
				8000
			);
		} finally {
			saving = false;
		}
	}

	async function make() {
		const lacks = missingSentence(picks);
		if (lacks) {
			toasts.show('warn', 'Not yet', lacks);
			return;
		}
		busy = true;
		try {
			const built = await api.buildPersona(voice, picks, libraryName.trim() || null);
			toasts.show(
				'ok',
				`${built.name} is on the shelf`,
				'An ordinary persona now: edit it like any other.'
			);
			forget();
			await goto(then === 'new' ? `/new?persona=${built.id}` : `/library/personas/${built.id}`);
		} catch (error) {
			toasts.show('danger', 'Not made', error instanceof Error ? error.message : undefined, 8000);
		} finally {
			busy = false;
		}
	}
</script>

<div class="outer" class:wide={wide.current}>
	{#if wide.current}<LibraryRail shelf="personas" />{/if}
	<div class="screen">
		<AppBar
			sections={!wide.current}
			title="Build a persona"
			sub={loaded ? builderLine(slots, picks) : undefined}
			back={then === 'new' ? '/new' : '/library'}
		>
			{#snippet actions()}
				<button type="button" class="pill" onclick={randomAll}>Fill the rest at random</button>
			{/snippet}
		</AppBar>
		<div class="controls">
			<div class="seg" role="radiogroup" aria-label="Voice">
				{#each VOICES as v (v.id)}
					<button
						type="button"
						role="radio"
						aria-checked={voice === v.id}
						onclick={() => changeVoice(v.id)}>{v.label}</button
					>
				{/each}
			</div>
			<div class="seg" role="tablist" aria-label="View">
				<button
					type="button"
					role="tab"
					aria-selected={view === 'slots'}
					onclick={() => (view = 'slots')}>Slots</button
				>
				<button
					type="button"
					role="tab"
					aria-selected={view === 'read'}
					onclick={() => (view = 'read')}>Read it</button
				>
			</div>
		</div>
		<main>
			{#if !loaded}
				<p class="muted">Reading the pieces…</p>
			{:else if view === 'read'}
				{#if previewError}
					<p class="muted">{previewError}</p>
				{:else if preview}
					<p class="prose persona">{preview.text}</p>
				{:else}
					<p class="muted">Pick a piece to see the persona.</p>
				{/if}
			{:else}
				{#each groups as g (g.key)}
					{@const chosen = pickedIn(g)}
					<div class="row">
						<button
							type="button"
							class="open"
							aria-haspopup="dialog"
							aria-label="{g.label}: {chosen.length
								? chosen.map((p) => p.name).join(', ')
								: 'nothing picked'}"
							onclick={() => openRow(g)}
						>
							<span class="what">
								<span
									class="label"
									class:picked={chosen.length > 0}
									class:needed={!chosen.length && neededIn(g)}>{g.label}</span
								>
								{#if chosen.length}
									<span class="value">{chosen.map((p) => p.name).join(', ')}</span>
								{:else}
									<span class="value muted"
										>{g.slots.length > 1
											? `One paragraph, up to ${g.slots.length} pieces`
											: 'Pick one, or leave it'}</span
									>
								{/if}
							</span>
							<span class="chev" aria-hidden="true">›</span>
						</button>
						<button type="button" class="random" onclick={() => randomRow(g)}>Random</button>
					</div>
				{/each}
			{/if}
		</main>
		<footer class="foot">
			{#if renaming}
				<input
					class="input"
					type="text"
					aria-label="Library name"
					bind:value={libraryName}
					maxlength="200"
					placeholder={preview?.name ?? 'from the name piece'}
					onblur={() => (renaming = false)}
					onkeydown={(e) => {
						if (e.key === 'Enter' || e.key === 'Escape') renaming = false;
					}}
				/>
			{:else}
				<span class="shelved">
					<span class="muted small">Will be shelved as</span>
					<span class="name"
						><span class="mono">{shelvedAs ?? 'the name piece'}</span>
						<button type="button" class="change" onclick={() => (renaming = true)}>change</button
						></span
					>
				</span>
			{/if}
			<button class="btn primary" type="button" onclick={make} disabled={busy}>
				{busy ? 'Making…' : 'Make persona'}
			</button>
		</footer>
	</div>
</div>

<Sheet
	bind:open={groupOpen}
	title={group?.label ?? 'Slot'}
	hint={group
		? `${neededIn(group) ? 'needed · ' : ''}${voice} voice · ${group.slots.reduce((n, s) => n + piecesOf(s.key).length, 0)} pieces`
		: undefined}
	max="86%"
>
	{#if group}
		<p class="muted intro">
			{neededIn(group)
				? 'A persona is not made without it. Picks apply as you tap.'
				: 'Optional. Picks apply as you tap; a picked piece shows its whole paragraph.'}
		</p>
		{#each group.slots as slot (slot.key)}
			{@const options = piecesOf(slot.key)}
			{@const chosen = picks[slot.key] ?? []}
			<section class="pool" aria-label="{slot.label} pieces">
				{#if group.slots.length > 1}<h4>{slot.label}</h4>{/if}
				{#each options as piece (piece.id)}
					{@const on = chosen.includes(piece.id)}
					{@const shown = pieceBlurb(piece)}
					<div class="opt" class:on>
						<button
							type="button"
							class="pick"
							role="checkbox"
							aria-checked={on}
							onclick={() => toggle(slot.key, piece.id)}
						>
							<span class="dot" aria-hidden="true"></span>
							<span class="text">
								<b>{piece.name}</b>
								{#if on}
									<small class="prose full">{piece.text}</small>
								{:else}
									<small class:prose={!shown.note}>{shown.text}</small>
								{/if}
							</span>
						</button>
						{#if on}
							<a class="edit" href="/library/pieces/{piece.id}?back=builder">Edit the piece</a>
						{/if}
					</div>
				{/each}
				{#if !options.length}
					<p class="muted">Nothing here in the {voice} voice yet.</p>
				{/if}
				{#if group.slots.length > 1}
					<button type="button" class="link" onclick={() => writeNew(slot)}
						>+ Write a new {slot.label.toLowerCase()} piece</button
					>
				{/if}
			</section>
		{/each}
		<div class="sheetfoot">
			<button type="button" class="btn ghost" onclick={() => group && randomRow(group)}
				>Random</button
			>
			{#if group.slots.length === 1}
				<button
					type="button"
					class="btn ghost gold"
					onclick={() => group && writeNew(group.slots[0])}>+ Write a new one</button
				>
			{/if}
			<button type="button" class="btn primary" onclick={() => (groupOpen = false)}>Done</button>
		</div>
	{/if}
</Sheet>

<Sheet
	bind:open={sheetOpen}
	title={sheetSlot ? `New ${sheetSlot.label.toLowerCase()} piece` : 'New piece'}
	hint="written in the {voice} voice"
>
	<form class="sheetform" onsubmit={savePiece}>
		{#if sheetSlot?.key === 'name'}
			<label class="field">
				<span>Full name, as the persona opens</span>
				<input class="input" type="text" bind:value={fullName} maxlength="100" required />
			</label>
			<label class="field">
				<span>Short name, used after the first mention</span>
				<input class="input" type="text" bind:value={shortName} maxlength="100" required />
			</label>
		{:else}
			<label class="field">
				<span>Name, for the picker</span>
				<input class="input" type="text" bind:value={pieceName} maxlength="200" required />
			</label>
			<label class="field">
				<span>The paragraph</span>
				<textarea class="input prose" rows="6" bind:value={pieceText} required></textarea>
			</label>
			<div class="tokens">
				<span class="muted">Write the persona's name as</span>
				<button type="button" class="chip" onclick={() => insert('{name}')}>{'{name}'}</button>
				<button type="button" class="chip" onclick={() => insert('{short}')}>{'{short}'}</button>
			</div>
			<p class="muted small">
				Keep to this slot: a piece that mentions another slot can contradict the pieces picked
				beside it.
			</p>
		{/if}
		<button class="btn primary" type="submit" disabled={!sheetReady || saving}>
			{saving ? 'Saving…' : 'Save and pick it'}
		</button>
	</form>
</Sheet>

<style>
	/* From 900 px the library's rail sits beside this screen, as it does beside the editor. */
	.outer {
		height: 100%;
		display: grid;
		grid-template-columns: minmax(0, 1fr);
	}
	.outer.wide {
		grid-template-columns: 340px minmax(0, 1fr);
	}
	/* Beside the rail the screen is the pane, not the centred 860 px frame of a lone wide screen. */
	.outer.wide .screen {
		max-width: none;
		margin-inline: 0;
	}
	.outer.wide .controls,
	.outer.wide main,
	.outer.wide .foot {
		margin: 0;
		max-width: 760px;
		padding-inline: 24px;
	}
	.screen {
		min-height: 0;
		height: 100%;
		display: flex;
		flex-direction: column;
	}
	.pill {
		appearance: none;
		display: inline-flex;
		align-items: center;
		min-height: 36px;
		padding: 0 12px;
		border-radius: var(--r-pill);
		border: 1px solid var(--line-strong);
		background: transparent;
		color: var(--fg-2);
		font-weight: 600;
		font-size: 0.82rem;
		white-space: nowrap;
	}
	.controls {
		display: flex;
		gap: 10px;
		align-items: center;
		justify-content: space-between;
		padding: 10px 14px 0;
		width: 100%;
		max-width: 720px;
		margin: 0 auto;
	}
	.seg {
		display: inline-flex;
		padding: 3px;
		gap: 2px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--line);
	}
	.seg button {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--fg-2);
		font-size: 0.85rem;
		font-weight: 500;
		padding: 6px 14px;
		min-height: 32px;
		border-radius: var(--r-pill);
	}
	.seg button[aria-checked='true'],
	.seg button[aria-selected='true'] {
		background: var(--gold);
		color: var(--gold-ink);
	}
	main {
		flex: 1;
		min-height: 0;
		overflow: auto;
		display: grid;
		align-content: start;
		padding: 12px 14px 24px;
		width: 100%;
		max-width: 720px;
		margin: 0 auto;
	}
	.persona {
		font-size: 0.98rem;
		line-height: 1.6;
		white-space: pre-line;
		color: var(--fg);
	}
	/* A row: the button that opens the slot's pool covers it, and Random sits on top of it. */
	.row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto 20px;
		align-items: center;
		border-bottom: 1px solid var(--line);
	}
	.row:last-child {
		border-bottom: 0;
	}
	.open {
		grid-column: 1 / -1;
		grid-row: 1;
		appearance: none;
		border: 0;
		background: transparent;
		color: inherit;
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: center;
		gap: 10px;
		text-align: left;
		padding: 12px 2px;
		min-height: 56px;
	}
	.what {
		display: grid;
		gap: 1px;
		min-width: 0;
		padding-right: 72px; /* room for Random, which sits over the row */
	}
	.label {
		font-size: 0.72rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--muted);
		font-weight: 600;
	}
	.label.picked {
		color: var(--gold-text);
	}
	.label.needed {
		color: var(--warn);
	}
	.value {
		font-weight: 600;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.value.muted {
		font-weight: 400;
	}
	.chev {
		color: var(--muted);
	}
	.random {
		grid-column: 2;
		grid-row: 1;
		position: relative;
		z-index: 1;
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--gold-text);
		font-size: 0.76rem;
		font-weight: 600;
		padding: 4px 6px;
		min-height: 32px;
		margin-right: 8px;
	}
	.foot {
		flex: none;
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 10px 16px calc(14px + var(--safe-bottom));
		border-top: 1px solid var(--line);
		background: var(--bg);
		width: 100%;
		max-width: 720px;
		margin: 0 auto;
	}
	.foot .input {
		flex: 1;
		min-height: 44px;
		padding: 8px 12px;
	}
	.shelved {
		flex: 1;
		min-width: 0;
		display: grid;
	}
	.shelved .small {
		font-size: 0.74rem;
	}
	.shelved .name {
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.mono {
		font-family: var(--font-mono);
		font-size: 0.9rem;
	}
	.change {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--gold-text);
		font-size: 0.78rem;
		font-weight: 600;
		padding: 2px 4px;
	}
	.intro {
		font-size: 0.8rem;
		line-height: 1.4;
	}
	.pool {
		display: grid;
		gap: 8px;
	}
	.pool h4 {
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
		font-weight: 600;
	}
	.opt {
		display: grid;
		border-radius: 12px;
		border: 1px solid var(--line);
		background: var(--bg);
		overflow: hidden;
	}
	.opt.on {
		border-color: var(--gold);
		box-shadow: 0 0 0 3px var(--gold-soft);
	}
	.pick {
		appearance: none;
		display: flex;
		gap: 10px;
		align-items: flex-start;
		text-align: left;
		padding: 12px;
		border: 0;
		background: transparent;
		color: var(--fg);
	}
	.dot {
		width: 16px;
		height: 16px;
		margin-top: 3px;
		flex: none;
		border-radius: 50%;
		border: 1.5px solid var(--muted);
	}
	.opt.on .dot {
		border-color: var(--gold);
		background: radial-gradient(circle, var(--gold) 45%, transparent 50%);
	}
	.text {
		min-width: 0;
		display: grid;
		gap: 2px;
	}
	.text small {
		color: var(--fg-2);
		font-size: 0.85rem;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.text small.full {
		display: block;
		font-size: 0.88rem;
		line-height: 1.45;
		white-space: pre-line;
	}
	.edit {
		justify-self: end;
		color: var(--gold-text);
		font-size: 0.78rem;
		font-weight: 600;
		text-decoration: none;
		padding: 0 18px 10px;
	}
	.link {
		appearance: none;
		justify-self: start;
		border: 0;
		background: transparent;
		color: var(--gold-text);
		font-weight: 600;
		font-size: 0.82rem;
		padding: 6px 0;
	}
	.sheetfoot {
		position: sticky;
		bottom: calc(-18px - var(--safe-bottom));
		display: flex;
		gap: 8px;
		padding: 8px 0 4px;
		background: var(--surface);
		border-top: 1px solid var(--line);
	}
	.sheetfoot .btn.ghost {
		flex: 1;
	}
	.sheetfoot .gold {
		color: var(--gold-text);
	}
	.sheetform {
		display: grid;
		gap: 12px;
	}
	.tokens {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		align-items: center;
		font-size: 0.85rem;
	}
	.small {
		font-size: 0.8rem;
	}
</style>
