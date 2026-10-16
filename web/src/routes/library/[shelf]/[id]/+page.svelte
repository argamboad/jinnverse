<script lang="ts">
	import { page } from '$app/state';
	import { untrack } from 'svelte';
	import AppBar from '#lib/AppBar.svelte';
	import LibraryRail from '#lib/LibraryRail.svelte';
	import SaveBar from '#lib/SaveBar.svelte';
	import Sheet from '#lib/Sheet.svelte';
	import {
		api,
		ApiError,
		type Defaults,
		type EntryFull,
		type HistoryEntry,
		type Shelf
	} from '#lib/api.ts';
	import { guardLeaving } from '#lib/leaveGuard.ts';
	import { DESCRIPTION_LENGTH, remaining, saveNote, sentDescription } from '#lib/library.ts';
	import { Media } from '#lib/media.svelte.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	/** One library entry, in its editor: a phone screen of its own, or the pane beside the
	 * library's rail on a wide window, with the saved versions in a drawer. Changes wait in the
	 * fields until the save bar saves them. */
	const shelf = $derived(page.params.shelf as Shelf);
	const id = $derived(page.params.id ?? 'new');
	const creating = $derived(id === 'new');
	const one = $derived(
		shelf === 'characters' ? 'character' : shelf === 'personas' ? 'persona' : 'snippet'
	);
	/** The description's hint, one per shelf: what a note for the lists sounds like there. */
	const descriptionHint = $derived(
		shelf === 'characters'
			? 'The innkeeper of the Gilded Heron'
			: shelf === 'personas'
				? 'A journeyman cooper, thirty, travelling between contracts'
				: 'How the band is introduced'
	);

	/** The library is a workspace from here: the rail on the left, the editor beside it. */
	const wideWindow = new Media('(min-width: 900px)');
	const wide = $derived(wideWindow.current);

	let entry = $state<EntryFull | null>(null);
	let name = $state('');
	let text = $state('');
	let opening = $state('');
	let description = $state('');
	let version = $state(0);
	let loaded = $state(false);
	let busy = $state(false);
	/** The entry as the server has it, when a save found it changed elsewhere. */
	let theirs = $state<EntryFull | null>(null);
	let history = $state<HistoryEntry[] | null>(null);
	let historyOpen = $state(false);
	let deleting = $state(false);
	/** For a persona: which one plays in every story that names none. */
	let defaults = $state<Defaults | null>(null);
	const isDefault = $derived(entry !== null && defaults?.default_persona_id === entry.id);

	const dirty = $derived(
		creating
			? name.trim().length > 0 || text.trim().length > 0 || description.trim().length > 0
			: entry !== null &&
					(name !== entry.name ||
						text !== entry.text ||
						opening !== (entry.opening ?? '') ||
						description.trim() !== (entry.description ?? ''))
	);
	const ready = $derived(
		name.trim().length > 0 && text.trim().length > 0 && remaining(description) >= 0 && !busy
	);
	const barVisible = $derived(dirty || theirs !== null);
	const saved = $derived(
		entry
			? new Date(entry.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
			: ''
	);

	const guard = guardLeaving(() => dirty);

	// The wide rail opens another entry without leaving this page: read it whenever the id changes.
	let shownKey = '';
	$effect(() => {
		const key = `${shelf}/${id}`;
		if (key !== shownKey) {
			shownKey = key;
			untrack(() => void open());
		}
	});

	async function open() {
		const [target, wanted] = [shelf, id];
		entry = null;
		theirs = null;
		history = null;
		historyOpen = false;
		deleting = false;
		name = text = opening = description = '';
		loaded = false;
		if (creating) {
			loaded = true;
			return;
		}
		if (target === 'personas') {
			api
				.defaults()
				.then((d) => (defaults = d))
				.catch(() => undefined);
		}
		try {
			const found = await api.entry(target, wanted);
			if (wanted === id) take(found);
		} catch (error) {
			toasts.show(
				'danger',
				`Could not open the ${one}`,
				error instanceof Error ? error.message : undefined
			);
		} finally {
			loaded = true;
		}
	}

	function take(found: EntryFull) {
		entry = found;
		name = found.name;
		text = found.text;
		opening = found.opening ?? '';
		description = found.description ?? '';
		version = found.version;
		theirs = null;
	}

	function discard() {
		if (entry) take(entry);
		else name = text = opening = description = '';
	}

	async function save() {
		if (!ready) return;
		busy = true;
		try {
			if (creating) {
				const made = await api.createEntry(shelf, {
					name: name.trim(),
					text,
					opening: shelf === 'characters' ? opening.trim() || null : undefined,
					description: sentDescription(description)
				});
				toasts.show('ok', `${made.name} is on the shelf`);
				await guard.leave(`/library/${shelf}/${made.id}`, { replaceState: true });
			} else {
				const saved = await api.saveEntry(shelf, id, {
					version,
					name: name.trim(),
					text,
					...(shelf === 'characters' ? { opening: opening.trim() || null } : {}),
					description: sentDescription(description)
				});
				take(saved);
				history = null; // a new version is in it now
				if (historyOpen) void loadHistory();
				toasts.show(
					'ok',
					`Saved as v${saved.version}`,
					'Every story using it reads the new text from its next turn.'
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

	function isConflict(body: unknown): body is { message: string; current: EntryFull } {
		return typeof body === 'object' && body !== null && 'current' in body;
	}

	function takeTheirs() {
		if (theirs) take(theirs);
	}

	async function toggleHistory() {
		historyOpen = !historyOpen;
		if (historyOpen && history === null) await loadHistory();
	}

	async function loadHistory() {
		try {
			history = await api.history(shelf, id);
		} catch {
			history = [];
		}
	}

	function restore(h: HistoryEntry) {
		name = h.name;
		text = h.text;
		opening = h.opening ?? '';
		description = h.description ?? '';
		if (!wide) historyOpen = false;
		toasts.show(
			'info',
			`Version ${h.version} is in the editor`,
			'Save to make it the current one.'
		);
	}

	/** Makes this persona the default, or stops it being one; saved at once, like a dial. */
	async function toggleDefault() {
		if (!entry) return;
		try {
			defaults = await api.setDefaults(isDefault ? null : entry.id);
			toasts.show(
				'ok',
				isDefault ? `${entry.name} is the default persona` : 'No default persona',
				isDefault
					? 'Every story that names none plays as them.'
					: 'A story that names none plays as nobody in particular.'
			);
		} catch (error) {
			toasts.show('danger', 'Not set', error instanceof Error ? error.message : undefined);
		}
	}

	async function remove() {
		busy = true;
		try {
			await api.deleteEntry(shelf, id);
			toasts.show('ok', `Deleted ${entry?.name ?? 'the ' + one}`);
			await guard.leave('/library');
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

{#snippet versions()}
	{#if history === null}
		<p class="muted">Reading…</p>
	{:else if history.length === 0}
		<p class="muted">Nothing yet.</p>
	{:else}
		<div class="versions">
			{#each history as h (h.version)}
				<div class="version" class:current={h.version === entry?.version}>
					<div class="vhead">
						<b>v{h.version}</b>
						<span class="muted small"
							>{new Date(h.saved_at).toLocaleString(undefined, {
								month: 'short',
								day: 'numeric',
								hour: '2-digit',
								minute: '2-digit'
							})}</span
						>
						{#if h.version !== entry?.version}
							<button type="button" class="link" onclick={() => restore(h)}
								>Put in the editor</button
							>
						{:else}
							<span class="chip gold">current</span>
						{/if}
					</div>
					<p class="prose vtext">{h.text}</p>
				</div>
			{/each}
		</div>
	{/if}
{/snippet}

<div class={wide ? 'libwide' : 'screen'}>
	{#if wide}
		<LibraryRail
			{shelf}
			current={entry?.id}
			stamp={entry ? `${entry.id}:${entry.version}:${entry.name}` : ''}
		/>
	{/if}
	<div class="pane">
		{#if wide}
			<header class="bar">
				<div class="title">
					<h1>{creating ? `New ${one}` : (entry?.name ?? one)}</h1>
					{#if entry}<span class="sub">{one} · v{entry.version} · saved {saved}</span>{/if}
				</div>
				<div class="grow"></div>
				{#if entry?.used_by.length}
					<span class="muted used">Used by</span>
					{#each entry.used_by.slice(0, 2) as story (story)}<span class="chip">{story}</span>{/each}
					{#if entry.used_by.length > 2}
						<span class="chip" title={entry.used_by.slice(2).join(', ')}
							>+{entry.used_by.length - 2}</span
						>
					{/if}
				{/if}
				{#if entry}
					<button
						type="button"
						class="pill"
						class:on={historyOpen}
						aria-expanded={historyOpen}
						onclick={toggleHistory}>History · {entry.version}</button
					>
				{/if}
			</header>
		{:else}
			<AppBar
				title={creating ? `New ${one}` : (entry?.name ?? one)}
				sub={entry ? `${one} · v${entry.version}` : undefined}
				back="/library"
			>
				{#snippet actions()}
					{#if entry}
						<button type="button" class="pill" onclick={toggleHistory}>History</button>
					{/if}
				{/snippet}
			</AppBar>
		{/if}

		<div class="body" class:drawer={wide && historyOpen}>
			<main>
				{#if !loaded}
					<p class="muted center">Opening…</p>
				{:else if !creating && !entry}
					<p class="muted center">There is no {one} with that id.</p>
				{:else}
					{#if !wide && entry?.used_by.length}
						<p class="usedline">
							<span>Used by</span>
							{#each entry.used_by as story (story)}<span class="chip">{story}</span>{/each}
							<span>· a save reaches it from its next turn</span>
						</p>
					{/if}
					{#if theirs}
						<div class="conflict" role="alert">
							<b>This {one} changed somewhere else since you opened it.</b>
							<p class="muted">Nothing was saved. Their text is below; yours is in the editor.</p>
							<pre class="prose">{theirs.text}</pre>
							<div class="row">
								<button type="button" class="btn primary" onclick={save}
									>Replace it with mine</button
								>
								<button type="button" class="btn ghost" onclick={takeTheirs}>Take theirs</button>
							</div>
						</div>
					{/if}
					<div class="pair">
						<label class="field">
							<span>Name</span>
							<input
								class="input"
								id="entry-name"
								type="text"
								bind:value={name}
								maxlength="200"
								placeholder={shelf === 'snippets' ? 'storm (typed as :storm)' : 'A name'}
							/>
						</label>
						<label class="field">
							<span class="spread"
								><span>Description <small class="muted">· for lists only</small></span>
								<small class="count" class:over={remaining(description) < 0}
									>{description.length} / {DESCRIPTION_LENGTH}</small
								></span
							>
							<input
								class="input"
								id="entry-description"
								type="text"
								bind:value={description}
								placeholder={descriptionHint}
							/>
						</label>
					</div>
					{#if shelf === 'personas' && !creating && entry}
						<div class="switch-row">
							<span>
								<b>Default persona</b>
								<small class="muted">Plays in every story that names none.</small>
							</span>
							<button
								type="button"
								class="toggle"
								role="switch"
								aria-checked={isDefault}
								aria-label="Default persona"
								onclick={toggleDefault}
							></button>
						</div>
					{/if}
					<label class="field">
						<span
							>{shelf === 'characters'
								? 'The card'
								: shelf === 'personas'
									? 'Who you are'
									: 'The text'}</span
						>
						<textarea
							class="input prose doc"
							id="entry-text"
							bind:value={text}
							rows={shelf === 'snippets' ? 4 : wide ? 12 : 9}
							placeholder={shelf === 'characters'
								? 'Who they are, how they speak, the world they live in…'
								: ''}></textarea>
					</label>
					{#if shelf === 'characters'}
						<label class="field">
							<span
								>Opening <small class="muted">· the scene a story starts on, optional</small></span
							>
							<textarea class="input prose doc" id="entry-opening" bind:value={opening} rows="4"
							></textarea>
						</label>
					{/if}
					{#if !creating}
						{#if deleting}
							<div class="confirm">
								<span class="muted small">Delete {entry?.name}?</span>
								<button type="button" class="btn danger" onclick={remove} disabled={busy}
									>Delete</button
								>
								<button type="button" class="btn ghost" onclick={() => (deleting = false)}
									>Keep</button
								>
							</div>
						{:else}
							<button type="button" class="delete" onclick={() => (deleting = true)}
								>Delete this {one}…</button
							>
						{/if}
						{#if entry?.used_by.length}
							<p class="muted small">It cannot be deleted while a story uses it.</p>
						{/if}
					{/if}
				{/if}
			</main>
			{#if wide && historyOpen}
				<aside class="history" aria-label="Every saved version">
					<div class="hhead">
						<h3>Every saved version</h3>
						<small class="muted">newest first</small>
					</div>
					{@render versions()}
				</aside>
			{/if}
		</div>

		{#if barVisible}
			<SaveBar
				note={creating
					? 'Not on the shelf yet'
					: saveNote(one, entry?.used_by.length ?? 0, version + 1, wide)}
				saveLabel={creating ? `Add the ${one}` : `Save as v${version + 1}`}
				{busy}
				disabled={!ready}
				onsave={save}
				ondiscard={discard}
			/>
		{/if}
	</div>
</div>

{#if !wide}
	<Sheet bind:open={historyOpen} title="Every saved version" hint="newest first">
		{@render versions()}
	</Sheet>
{/if}

<style>
	.screen {
		height: 100%;
		display: flex;
		flex-direction: column;
	}
	/* From 900 px the library is a workspace: the rail, and the editor beside it. */
	.libwide {
		height: 100%;
		display: grid;
		grid-template-columns: 340px minmax(0, 1fr);
	}
	.pane {
		flex: 1;
		min-height: 0;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}
	.bar {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 0 24px;
		min-height: 62px;
		border-bottom: 1px solid var(--line);
		flex-wrap: nowrap;
	}
	.title {
		min-width: 0;
		display: grid;
	}
	.title h1 {
		font-size: 1.05rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.sub {
		font-size: 0.74rem;
		color: var(--muted);
	}
	.grow {
		flex: 1;
	}
	.used {
		font-size: 0.8rem;
		white-space: nowrap;
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
	.pill.on {
		border-color: var(--gold);
		background: var(--gold-soft);
		color: var(--gold-text);
	}
	.body {
		flex: 1;
		min-height: 0;
		display: grid;
		grid-template-columns: minmax(0, 1fr);
	}
	.body.drawer {
		grid-template-columns: minmax(0, 1fr) 300px;
	}
	main {
		min-height: 0;
		overflow: auto;
		display: grid;
		gap: 14px;
		align-content: start;
		padding: 14px 16px 24px;
		max-width: 760px;
		width: 100%;
	}
	.libwide main {
		padding: 18px 24px 24px;
	}
	.screen main {
		margin: 0 auto;
	}
	.center {
		text-align: center;
		padding: 32px;
	}
	.usedline {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		align-items: center;
		font-size: 0.8rem;
		color: var(--muted);
	}
	.pair {
		display: grid;
		gap: 14px;
	}
	/* Name and description share a row only where there is room for a long name; the owner's
	   names run long and the descriptions are mostly empty, so the name gets the wider column. */
	@media (min-width: 1100px) {
		.libwide .pair {
			grid-template-columns: 1.4fr 1fr;
			gap: 12px;
		}
	}
	.spread {
		display: flex;
		justify-content: space-between;
		gap: 8px;
	}
	textarea.doc {
		resize: vertical;
		line-height: 1.55;
		font-size: 1rem;
	}
	.libwide textarea.doc {
		padding: 14px 16px;
		line-height: 1.6;
	}
	.btn.danger {
		background: var(--danger);
		color: #fff;
	}
	.small {
		font-size: 0.82rem;
	}
	.count {
		color: var(--muted);
	}
	.count.over {
		color: var(--danger);
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
	.confirm {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
		align-items: center;
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
	.switch-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 10px 12px;
		border-radius: var(--r-s);
		background: var(--surface);
		border: 1px solid var(--line);
	}
	.switch-row span {
		display: grid;
		gap: 1px;
	}
	.switch-row small {
		font-size: 0.78rem;
	}
	.toggle {
		position: relative;
		width: 48px;
		height: 28px;
		flex: none;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--line-strong);
	}
	.toggle::after {
		content: '';
		position: absolute;
		top: 3px;
		left: 3px;
		width: 20px;
		height: 20px;
		border-radius: 50%;
		background: var(--fg-2);
		transition: transform 0.18s ease;
	}
	.toggle[aria-checked='true'] {
		background: var(--gold);
		border-color: transparent;
	}
	.toggle[aria-checked='true']::after {
		transform: translateX(20px);
		background: var(--gold-ink);
	}
	.history {
		border-left: 1px solid var(--line);
		background: var(--bg-2);
		min-height: 0;
		overflow: auto;
		padding: 16px;
		display: grid;
		gap: 10px;
		align-content: start;
	}
	.hhead {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
	}
	.hhead h3 {
		font-size: 0.95rem;
	}
	.hhead small {
		font-size: 0.74rem;
	}
	.versions {
		display: grid;
		gap: 10px;
	}
	.version {
		display: grid;
		gap: 6px;
		padding: 10px 12px;
		border-radius: var(--r-s);
		background: var(--surface-2);
		border: 1px solid var(--line);
	}
	.version.current {
		border-color: var(--gold);
	}
	.vhead {
		display: flex;
		gap: 8px;
		align-items: center;
		flex-wrap: wrap;
	}
	.vhead b {
		font-weight: 600;
	}
	.vhead .chip {
		margin-left: auto;
	}
	.vtext {
		font-size: 0.84rem;
		line-height: 1.45;
		color: var(--fg-2);
		white-space: pre-wrap;
		display: -webkit-box;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.link {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--gold-text);
		font-weight: 600;
		font-size: 0.76rem;
		padding: 4px 6px;
		margin-left: auto;
		min-height: 32px;
	}
</style>
