<script lang="ts">
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import AppBar from '#lib/AppBar.svelte';
	import LibraryRail from '#lib/LibraryRail.svelte';
	import SaveBar from '#lib/SaveBar.svelte';
	import { api, ApiError, type Piece, type Slot, type Voice } from '#lib/api.ts';
	import { guardLeaving } from '#lib/leaveGuard.ts';
	import { DESCRIPTION_LENGTH, remaining, sentDescription } from '#lib/library.ts';
	import { Media } from '#lib/media.svelte.ts';
	import { PIECE_VOICES } from '#lib/personaBuilder.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	const id = $derived(page.params.id ?? 'new');
	const creating = $derived(id === 'new');
	/** Where Back and a delete go: the builder when the editor was opened from it. */
	const backTo = $derived(
		page.url.searchParams.get('back') === 'builder'
			? '/library/personas/from-pieces'
			: '/library/pieces'
	);

	const wide = new Media('(min-width: 900px)');

	let slots = $state<Slot[]>([]);
	let piece = $state<Piece | null>(null);
	let slotKey = $state('look');
	let name = $state('');
	let voice = $state<Voice>('he');
	let text = $state('');
	let short = $state('');
	let description = $state('');
	let version = $state(0);
	let loaded = $state(false);
	let busy = $state(false);
	let deleting = $state(false);
	/** The piece as the server has it, when a save found it changed elsewhere. */
	let theirs = $state<Piece | null>(null);

	const slotLabel = $derived(slots.find((s) => s.key === slotKey)?.label ?? slotKey);
	const isName = $derived(slotKey === 'name');
	const dirty = $derived(
		creating
			? name.trim().length > 0 || text.trim().length > 0
			: piece !== null &&
					(name.trim() !== piece.name ||
						voice !== piece.voice ||
						text.trim() !== piece.text ||
						short.trim() !== (piece.short ?? '') ||
						description.trim() !== (piece.description ?? ''))
	);
	const ready = $derived(
		name.trim().length > 0 &&
			text.trim().length > 0 &&
			(!isName || short.trim().length > 0) &&
			remaining(description) >= 0 &&
			!busy
	);

	const guard = guardLeaving(() => dirty);

	onMount(async () => {
		try {
			slots = await api.pieceSlots();
			if (creating) {
				slotKey = page.url.searchParams.get('slot') ?? slots[1]?.key ?? 'look';
				return;
			}
			const found = (await api.pieces()).find((p) => p.id === id);
			if (found) take(found);
		} catch (error) {
			toasts.show(
				'danger',
				'Could not open the piece',
				error instanceof Error ? error.message : undefined
			);
		} finally {
			loaded = true;
		}
	});

	function take(found: Piece) {
		piece = found;
		slotKey = found.slot;
		name = found.name;
		voice = found.voice;
		text = found.text;
		short = found.short ?? '';
		description = found.description ?? '';
		version = found.version;
		theirs = null;
	}

	function discard() {
		if (piece) take(piece);
		else name = text = short = description = '';
	}

	function insert(token: string) {
		text = text ? `${text} ${token}` : token;
	}

	async function save() {
		if (!ready) return;
		busy = true;
		try {
			if (creating) {
				const made = await api.createPiece({
					slot: slotKey,
					voice,
					name: name.trim(),
					text: text.trim(),
					short: isName ? short.trim() : undefined,
					description: sentDescription(description)
				});
				toasts.show('ok', `${made.name} is in the pool`);
				take(made);
				await guard.leave(`/library/pieces/${made.id}`, { replaceState: true });
			} else {
				const saved = await api.savePiece(id, {
					version,
					name: name.trim(),
					voice,
					text: text.trim(),
					...(isName ? { short: short.trim() } : {}),
					description: sentDescription(description)
				});
				take(saved);
				toasts.show(
					'ok',
					`Saved as v${saved.version}`,
					'Personas already built from it keep the text they were made with.'
				);
			}
		} catch (error) {
			if (error instanceof ApiError && error.status === 409 && isConflict(error.body)) {
				theirs = error.body.current;
				version = theirs.version; // saving again replaces what is there now
			} else {
				toasts.show(
					'danger',
					'Not saved',
					error instanceof Error ? error.message : undefined,
					8000
				);
			}
		} finally {
			busy = false;
		}
	}

	function isConflict(body: unknown): body is { message: string; current: Piece } {
		return typeof body === 'object' && body !== null && 'current' in body;
	}

	function takeTheirs() {
		if (theirs) take(theirs);
	}

	async function remove() {
		busy = true;
		try {
			await api.deletePiece(id);
			toasts.show('ok', `Deleted ${piece?.name ?? 'the piece'}`);
			await guard.leave(backTo);
		} catch (error) {
			toasts.show(
				'danger',
				'Not deleted',
				error instanceof Error ? error.message : undefined,
				10000
			);
		} finally {
			busy = false;
			deleting = false;
		}
	}
</script>

<div class="outer" class:wide={wide.current}>
	{#if wide.current}<LibraryRail shelf="personas" />{/if}
	<div class="screen">
		<AppBar
			sections={!wide.current}
			title={creating ? 'New piece' : (piece?.name ?? 'Piece')}
			sub={piece ? `${slotLabel} · version ${piece.version}` : undefined}
			back={backTo}
		/>
		<main>
			{#if !loaded}
				<p class="muted center">Opening…</p>
			{:else if !creating && !piece}
				<p class="muted center">There is no piece with that id.</p>
			{:else}
				{#if theirs}
					<div class="conflict" role="alert">
						<b>This piece changed somewhere else since you opened it.</b>
						<p class="muted">Nothing was saved. Its text is below; yours is in the editor.</p>
						<pre class="prose">{theirs.text}</pre>
						<div class="row">
							<button type="button" class="btn primary" onclick={save}>Replace it with mine</button>
							<button type="button" class="btn ghost" onclick={takeTheirs}>Take theirs</button>
						</div>
					</div>
				{/if}
				{#if creating}
					<label class="field">
						<span>Slot</span>
						<select class="input" id="piece-slot" bind:value={slotKey}>
							{#each slots as s (s.key)}
								<option value={s.key}>{s.label}</option>
							{/each}
						</select>
					</label>
				{:else}
					<p class="slotline">
						<span class="chip gold">{slotLabel}</span>
						<span class="muted small">the slot cannot change</span>
					</p>
				{/if}
				<label class="field">
					<span>Name, for the picker</span>
					<input
						class="input"
						id="piece-name"
						type="text"
						bind:value={name}
						maxlength="200"
						placeholder={isName ? 'Allan Sanlúcar' : 'Penthouse'}
					/>
				</label>
				<div class="field">
					<span>Voice</span>
					<div class="seg" role="radiogroup" aria-label="Voice">
						{#each PIECE_VOICES as v (v.id)}
							<button
								type="button"
								role="radio"
								aria-checked={voice === v.id}
								onclick={() => (voice = v.id)}>{v.label}</button
							>
						{/each}
					</div>
				</div>
				<label class="field">
					<span
						>Description <small class="muted"
							>— a short note for lists, never sent to the model</small
						>
						<small class="count" class:over={remaining(description) < 0}
							>{description.length} / {DESCRIPTION_LENGTH}</small
						></span
					>
					<input
						class="input"
						id="piece-description"
						type="text"
						bind:value={description}
						placeholder="Across from the university, studio room"
					/>
				</label>
				<label class="field grow">
					<span>{isName ? 'The full name' : 'The paragraph'}</span>
					<textarea
						class="input prose"
						id="piece-text"
						bind:value={text}
						rows={isName ? 2 : 12}
						placeholder={isName ? 'Allan Sanlúcar El Kettani' : ''}></textarea>
				</label>
				{#if isName}
					<label class="field">
						<span>The short name <small class="muted">— used after the first mention</small></span>
						<input class="input" id="piece-short" type="text" bind:value={short} maxlength="100" />
					</label>
				{:else}
					<div class="tokens">
						<span class="muted">Write the persona's name as</span>
						<button type="button" class="chip" onclick={() => insert('{name}')}>{'{name}'}</button>
						<button type="button" class="chip" onclick={() => insert('{short}')}>{'{short}'}</button
						>
					</div>
					<p class="muted small">
						Shown as written: <code>{'{name}'}</code> and <code>{'{short}'}</code> are filled in when
						a persona is built. Keep to this slot: a piece that mentions another can contradict the pieces
						picked beside it.
					</p>
				{/if}
				{#if !creating}
					{#if deleting}
						<div class="foot">
							<span class="muted small">Delete {piece?.name}?</span>
							<button type="button" class="btn danger" onclick={remove} disabled={busy}
								>Delete</button
							>
							<button type="button" class="btn ghost" onclick={() => (deleting = false)}
								>Keep</button
							>
						</div>
					{:else}
						<button type="button" class="delete" onclick={() => (deleting = true)}
							>Delete this piece…</button
						>
					{/if}
				{/if}
				{#if !creating}
					<p class="muted small">
						Nothing depends on a piece: a persona built from it holds its own copy of the text.
					</p>
				{/if}
			{/if}
		</main>
		{#if dirty || theirs}
			<SaveBar
				note={creating ? 'Not in the pool yet' : 'Unsaved changes'}
				saveLabel={creating ? 'Add the piece' : `Save as v${version + 1}`}
				{busy}
				disabled={!ready}
				onsave={save}
				ondiscard={discard}
			/>
		{/if}
	</div>
</div>

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
	.outer.wide main {
		margin: 0;
		padding-inline: 24px;
	}
	.screen {
		min-height: 0;
		height: 100%;
		display: flex;
		flex-direction: column;
	}
	main {
		flex: 1;
		min-height: 0;
		overflow: auto;
		display: grid;
		gap: 14px;
		align-content: start;
		padding: 14px 16px 24px;
		max-width: 760px;
		width: 100%;
		margin: 0 auto;
	}
	.center {
		text-align: center;
		padding: 32px;
	}
	.slotline {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	textarea.input {
		resize: vertical;
		line-height: 1.55;
		font-size: 1rem;
	}
	.seg {
		display: inline-flex;
		padding: 3px;
		gap: 2px;
		width: max-content;
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
		padding: 6px 16px;
		min-height: 34px;
		border-radius: var(--r-pill);
	}
	.seg button[aria-checked='true'] {
		background: var(--gold);
		color: var(--gold-ink);
	}
	.count {
		float: right;
		color: var(--muted);
	}
	.count.over {
		color: var(--danger);
	}
	.tokens {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		align-items: center;
		font-size: 0.85rem;
	}
	.foot {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
		align-items: center;
	}
	.btn.danger {
		background: var(--danger);
		color: #fff;
	}
	.delete {
		appearance: none;
		justify-self: start;
		border: 0;
		background: transparent;
		color: var(--danger);
		font-weight: 600;
		font-size: 0.85rem;
		padding: 8px 0;
	}
	.small {
		font-size: 0.82rem;
	}
	.conflict {
		display: grid;
		gap: 10px;
		padding: 14px;
		border-radius: var(--r-m);
		border: 1px solid var(--warn);
		background: var(--surface);
	}
	.conflict pre {
		white-space: pre-wrap;
		margin: 0;
		max-height: 240px;
		overflow: auto;
		padding: 10px 12px;
		border-radius: var(--r-s);
		background: var(--surface-2);
		font-size: 0.9rem;
	}
	.row {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
</style>
