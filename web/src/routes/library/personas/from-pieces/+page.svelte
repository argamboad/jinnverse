<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import AppBar from '#lib/AppBar.svelte';
	import Sheet from '#lib/Sheet.svelte';
	import {
		api,
		type PersonaPreview,
		type Picks,
		type Piece,
		type Slot,
		type Voice
	} from '#lib/api.ts';
	import {
		VOICES,
		count,
		hasText,
		isNeeded,
		keeping,
		missingSentence,
		randomFor,
		toggled
	} from '#lib/personaBuilder.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	/** Where to go once the persona is made: back to the new-story form when it came from there. */
	const then = $derived(page.url.searchParams.get('then'));

	let voice = $state<Voice>('he');
	let slots = $state<Slot[]>([]);
	let pool = $state<Piece[]>([]);
	let picks = $state<Picks>({});
	/** The slot whose pool is open. */
	let open = $state<string | null>(null);
	let loaded = $state(false);

	let preview = $state<PersonaPreview | null>(null);
	let previewError = $state<string | null>(null);
	let reading = $state(false);
	let libraryName = $state('');
	let busy = $state(false);

	let sheetOpen = $state(false);
	let sheetSlot = $state<Slot | null>(null);
	let pieceName = $state('');
	let pieceText = $state('');
	let fullName = $state('');
	let shortName = $state('');
	let saving = $state(false);

	const picked = $derived(count(picks));
	const sheetReady = $derived(
		sheetSlot?.key === 'name'
			? fullName.trim().length > 0 && shortName.trim().length > 0
			: pieceName.trim().length > 0 && pieceText.trim().length > 0
	);

	onMount(async () => {
		try {
			[slots, pool] = await Promise.all([api.pieceSlots(), api.pieces(voice)]);
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

	function pieceById(id: string): Piece | undefined {
		return pool.find((p) => p.id === id);
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

	function random(slot: Slot) {
		const id = randomFor(
			piecesOf(slot.key).map((p) => p.id),
			Math.random()
		);
		if (id === null) {
			toasts.show('info', `No ${slot.label.toLowerCase()} piece yet`, 'Write the first one.');
			return;
		}
		picks = { ...picks, [slot.key]: [id] };
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

	function writeNew(slot: Slot) {
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
			open = slot.key;
			sheetOpen = false;
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
			await goto(then === 'new' ? `/new?persona=${built.id}` : `/library/personas/${built.id}`);
		} catch (error) {
			toasts.show('danger', 'Not made', error instanceof Error ? error.message : undefined, 8000);
		} finally {
			busy = false;
		}
	}
</script>

<div class="screen">
	<AppBar title="Build a persona" back={then === 'new' ? '/new' : '/library'}>
		{#snippet actions()}
			<button type="button" class="link" onclick={randomAll}>Random all</button>
		{/snippet}
	</AppBar>
	<div class="layout">
		<main class="slots">
			<div class="seg" role="tablist" aria-label="Voice">
				{#each VOICES as v (v.id)}
					<button
						type="button"
						role="tab"
						aria-selected={voice === v.id}
						onclick={() => changeVoice(v.id)}>{v.label}</button
					>
				{/each}
			</div>
			{#if !loaded}
				<p class="muted">Reading the pieces…</p>
			{/if}
			{#each slots as slot (slot.key)}
				{@const options = piecesOf(slot.key)}
				{@const chosen = picks[slot.key] ?? []}
				<section class="slot" aria-label={slot.label}>
					<div class="head">
						<button
							type="button"
							class="title"
							aria-expanded={open === slot.key}
							onclick={() => (open = open === slot.key ? null : slot.key)}
						>
							<h2>{slot.label}</h2>
							{#if isNeeded(slot.key) && !chosen.length}<span class="chip warn">needed</span>{/if}
						</button>
						<button
							type="button"
							class="dice"
							aria-label="Pick a {slot.label.toLowerCase()} piece at random"
							onclick={() => random(slot)}>⚄</button
						>
					</div>
					{#if chosen.length}
						<div class="chips">
							{#each chosen as id (id)}
								{@const piece = pieceById(id)}
								{#if piece}
									<button
										type="button"
										class="chip gold pickedchip"
										aria-label="Take back {piece.name}"
										onclick={() => toggle(slot.key, id)}
										>✓ {piece.name} <span aria-hidden="true">×</span></button
									>
								{/if}
							{/each}
						</div>
					{:else}
						<p class="muted none">
							{isNeeded(slot.key) ? 'Pick one' : 'None picked — optional'}
						</p>
					{/if}
					{#if open === slot.key}
						<div class="options" role="group" aria-label="{slot.label} pieces">
							{#each options as piece (piece.id)}
								{@const on = chosen.includes(piece.id)}
								<button
									type="button"
									class="opt"
									role="checkbox"
									aria-checked={on}
									onclick={() => toggle(slot.key, piece.id)}
								>
									<span class="dot" aria-hidden="true"></span>
									<span class="what">
										<b>{piece.name}</b>
										<small class="prose">{piece.text}</small>
									</span>
								</button>
							{/each}
							{#if !options.length}
								<p class="muted">Nothing here yet.</p>
							{/if}
							<button type="button" class="link new" onclick={() => writeNew(slot)}
								>+ New {slot.label.toLowerCase()} piece</button
							>
						</div>
					{/if}
				</section>
			{/each}
		</main>
		<aside class="side">
			<div class="pv">
				<button
					type="button"
					class="pvhead"
					aria-expanded={reading}
					onclick={() => (reading = !reading)}
				>
					<b>The persona · {picked} {picked === 1 ? 'piece' : 'pieces'}</b>
					<span aria-hidden="true">{reading ? '⌃' : '⌄'}</span>
				</button>
				{#if previewError}
					<p class="muted">{previewError}</p>
				{:else if preview}
					<p class="prose text" class:full={reading}>{preview.text}</p>
				{:else}
					<p class="muted">Pick a piece to see the persona.</p>
				{/if}
			</div>
		</aside>
	</div>
	<footer class="foot">
		<label class="field">
			<span>Library name</span>
			<input
				class="input"
				type="text"
				bind:value={libraryName}
				maxlength="200"
				placeholder={preview?.name ?? 'from the name piece'}
			/>
		</label>
		<button class="btn primary" type="button" onclick={make} disabled={busy}>
			{busy ? 'Making…' : 'Make persona'}
		</button>
	</footer>
</div>

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
	.screen {
		min-height: 100%;
		display: flex;
		flex-direction: column;
	}
	.link {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--gold-text);
		font-weight: 600;
		font-size: 0.85rem;
		padding: 8px;
		min-height: 36px;
	}
	.layout {
		flex: 1;
		display: grid;
		gap: 14px;
		align-content: start;
		padding: 12px 12px 8px;
		width: 100%;
		max-width: 720px;
		margin: 0 auto;
	}
	.slots {
		display: grid;
		gap: 10px;
		align-content: start;
	}
	.seg {
		display: inline-flex;
		padding: 3px;
		gap: 2px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--line);
		width: max-content;
	}
	.seg button {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--fg-2);
		font-size: 0.85rem;
		font-weight: 500;
		padding: 6px 16px;
		min-height: 34px;
		border-radius: var(--r-pill);
	}
	.seg button[aria-selected='true'] {
		background: var(--gold);
		color: var(--gold-ink);
	}
	.slot {
		display: grid;
		gap: 8px;
		padding: 10px 12px;
		border-radius: var(--r-m);
		background: var(--surface);
		border: 1px solid var(--line);
	}
	.head {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.title {
		appearance: none;
		border: 0;
		background: transparent;
		padding: 4px 0;
		min-height: 36px;
		display: flex;
		align-items: center;
		gap: 8px;
		flex: 1;
		text-align: left;
	}
	h2 {
		font-size: 0.78rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--gold-text);
	}
	.dice {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--muted);
		font-size: 1.3rem;
		width: 40px;
		height: 36px;
		border-radius: var(--r-s);
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.pickedchip {
		appearance: none;
		border: 1px solid var(--gold);
		font-size: 0.85rem;
		min-height: 30px;
	}
	.none {
		font-size: 0.85rem;
	}
	.options {
		display: grid;
		gap: 6px;
	}
	.opt {
		appearance: none;
		display: flex;
		gap: 10px;
		align-items: flex-start;
		text-align: left;
		padding: 10px;
		border-radius: var(--r-s);
		border: 1px solid var(--line);
		background: var(--bg);
	}
	.opt[aria-checked='true'] {
		border-color: var(--gold);
		box-shadow: 0 0 0 3px var(--gold-soft);
	}
	.dot {
		width: 16px;
		height: 16px;
		margin-top: 3px;
		flex: none;
		border-radius: 50%;
		border: 1.5px solid var(--muted);
	}
	.opt[aria-checked='true'] .dot {
		border-color: var(--gold);
		background: radial-gradient(circle, var(--gold) 45%, transparent 50%);
	}
	.what {
		min-width: 0;
		display: grid;
		gap: 2px;
	}
	.what small {
		color: var(--fg-2);
		font-size: 0.85rem;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.new {
		justify-self: start;
	}
	.pv {
		display: grid;
		gap: 6px;
		padding: 10px 12px;
		border-radius: var(--r-m);
		background: var(--surface-2);
		border: 1px solid var(--line);
	}
	.pvhead {
		appearance: none;
		border: 0;
		background: transparent;
		display: flex;
		justify-content: space-between;
		align-items: center;
		text-align: left;
		padding: 2px 0;
		min-height: 32px;
	}
	.text {
		color: var(--fg-2);
		font-size: 0.9rem;
		white-space: pre-line;
		display: -webkit-box;
		-webkit-line-clamp: 4;
		line-clamp: 4;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.text.full {
		display: block;
		overflow: visible;
	}
	.foot {
		position: sticky;
		bottom: 0;
		display: grid;
		gap: 10px;
		padding: 10px 12px calc(12px + var(--safe-bottom));
		background: var(--bg);
		border-top: 1px solid var(--line);
		width: 100%;
		max-width: 720px;
		margin: 0 auto;
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
	@media (min-width: 900px) {
		.layout {
			max-width: var(--frame);
			grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
			align-items: start;
		}
		.side {
			position: sticky;
			top: 70px;
		}
		.foot {
			max-width: var(--frame);
		}
	}
</style>
