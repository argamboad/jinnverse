<script lang="ts">
	import type { Extras } from '#lib/extras.svelte.ts';
	import type { StatusField, StatusKind, StatusScope } from '#lib/api.ts';
	import { grouped, parseWords, scopeNote } from '#lib/status.ts';

	/** The Status tab: the lines a story's replies open with, switched on and off, written by hand
	 * or taken from the starter set; the characters whose state is always sent; and what each line
	 * holds now, which can be corrected. Every change is saved as it is made. */
	let { extras }: { extras: Extras } = $props();

	const status = $derived(extras.status);
	const subjects = $derived(status ? grouped(status) : []);

	// --- the fields ---------------------------------------------------------------------------
	let editing = $state<string | null>(null);
	let label = $state('');
	let icon = $state('');
	let hint = $state('');
	let words = $state('');

	function edit(field: StatusField) {
		editing = field.key;
		label = field.label;
		icon = field.icon ?? '';
		hint = field.hint ?? '';
		words = (field.words ?? []).join(', ');
	}

	async function save(field: StatusField) {
		const ok = await extras.changeField(field.key, {
			label: label.trim(),
			icon: icon.trim() || null,
			hint: hint.trim() || null,
			...(field.kind === 'words' ? { words: parseWords(words) } : {})
		});
		if (ok) editing = null;
	}

	async function remove(field: StatusField) {
		if (await extras.removeField(field.key)) editing = null;
	}

	// --- a new field --------------------------------------------------------------------------
	let adding = $state(false);
	let newLabel = $state('');
	let newIcon = $state('');
	let newHint = $state('');
	let newScope = $state<StatusScope>('character');
	let newKind = $state<StatusKind>('text');
	let newWords = $state('');

	async function add(event: SubmitEvent) {
		event.preventDefault();
		if (!newLabel.trim()) return;
		const ok = await extras.addField({
			label: newLabel.trim(),
			icon: newIcon.trim() || null,
			hint: newHint.trim() || null,
			scope: newScope,
			kind: newKind,
			words: newKind === 'words' ? parseWords(newWords) : null
		});
		if (ok) {
			adding = false;
			newLabel = newIcon = newHint = newWords = '';
			newScope = 'character';
			newKind = 'text';
		}
	}

	// --- who is always sent -------------------------------------------------------------------
	let pin = $state('');

	async function addPin(event: SubmitEvent) {
		event.preventDefault();
		const name = pin.trim();
		if (!name || !status) return;
		if (await extras.setPins([...status.pins, name])) pin = '';
	}

	// --- what each line holds -----------------------------------------------------------------
	let setting = $state<string | null>(null);
	let draft = $state('');

	function begin(who: string, field: StatusField, value: string) {
		setting = `${who}\u0000${field.key}`;
		draft = value;
	}

	async function commit(who: string, field: StatusField) {
		if (await extras.setStatusValue(field.key, who, draft)) setting = null;
	}
</script>

<div class="stack">
	{#if !status}
		<p class="muted small">Reading…</p>
	{:else}
		<p class="muted small">
			A status block at the top of each reply — the day, the place, and for each character what they
			wear and how they feel — kept by the app, so it holds over a long story. A line reaches the
			story from its next turn.
		</p>

		<h4>Fields</h4>
		{#each status.fields as field (field.key)}
			<div class="item" class:off={!field.enabled}>
				<div class="line">
					<span class="ic" aria-hidden="true">{field.icon ?? '·'}</span>
					<span class="grow">
						<b>{field.label}</b>
						<span class="note">{scopeNote(field)}</span>
					</span>
					<button
						type="button"
						class="link"
						onclick={() => (editing === field.key ? (editing = null) : edit(field))}
						>{editing === field.key ? 'Close' : 'Edit'}</button
					>
					<button
						type="button"
						class="toggle"
						role="switch"
						aria-checked={field.enabled}
						aria-label={field.label}
						onclick={() => extras.changeField(field.key, { enabled: !field.enabled })}
					></button>
				</div>
				{#if editing === field.key}
					<form
						class="edit"
						onsubmit={(e) => {
							e.preventDefault();
							void save(field);
						}}
					>
						<label class="field"
							><span>Label</span><input
								class="input"
								id="sf-label-{field.key}"
								type="text"
								maxlength="60"
								bind:value={label}
								required
							/></label
						>
						<div class="two">
							<label class="field"
								><span>Icon</span><input
									class="input"
									id="sf-icon-{field.key}"
									type="text"
									maxlength="8"
									bind:value={icon}
									placeholder="optional"
								/></label
							>
							<span class="note pad">The key <code>{field.key}</code> never changes.</span>
						</div>
						<label class="field"
							><span>What the model writes</span><input
								class="input"
								id="sf-hint-{field.key}"
								type="text"
								maxlength="200"
								bind:value={hint}
								placeholder="what they are wearing now, briefly"
							/></label
						>
						{#if field.kind === 'words'}
							<label class="field"
								><span>Allowed words, separated by commas</span><input
									class="input"
									id="sf-words-{field.key}"
									type="text"
									bind:value={words}
									placeholder="Guarded, Teasing, Rattled"
								/></label
							>
						{/if}
						<div class="two">
							<button type="submit" class="btn primary">Save</button>
							<button type="button" class="btn ghost danger" onclick={() => remove(field)}
								>Delete, with what it holds</button
							>
						</div>
					</form>
				{/if}
			</div>
		{/each}

		{#each status.starters as starter (starter.key)}
			<div class="item starter">
				<div class="line">
					<span class="ic" aria-hidden="true">{starter.icon ?? '·'}</span>
					<span class="grow">
						<b>{starter.label}</b>
						<span class="note">{scopeNote(starter)} · not in this story</span>
					</span>
					<button type="button" class="btn tiny" onclick={() => extras.adoptStarters([starter.key])}
						>Add</button
					>
				</div>
			</div>
		{/each}

		{#if adding}
			<form class="add" onsubmit={add}>
				<label class="field"
					><span>Label</span><input
						class="input"
						id="sf-new-label"
						type="text"
						maxlength="60"
						bind:value={newLabel}
						required
						placeholder="Who she is with"
					/></label
				>
				<div class="two">
					<label class="field"
						><span>Icon</span><input
							class="input"
							id="sf-new-icon"
							type="text"
							maxlength="8"
							bind:value={newIcon}
							placeholder="optional"
						/></label
					>
					<label class="field"
						><span>Belongs to</span>
						<select class="input" id="sf-new-scope" bind:value={newScope}>
							<option value="character">Each character</option>
							<option value="scene">The scene</option>
						</select></label
					>
				</div>
				<label class="field"
					><span>What the model writes</span><input
						class="input"
						id="sf-new-hint"
						type="text"
						maxlength="200"
						bind:value={newHint}
						placeholder="the people next to her, briefly"
					/></label
				>
				<label class="field"
					><span>Kind</span>
					<select class="input" id="sf-new-kind" bind:value={newKind}>
						<option value="text">Any text</option>
						<option value="words">Words from a list</option>
					</select></label
				>
				{#if newKind === 'words'}
					<label class="field"
						><span>Allowed words, separated by commas</span><input
							class="input"
							id="sf-new-words"
							type="text"
							bind:value={newWords}
							required
							placeholder="Guarded, Teasing, Rattled"
						/></label
					>
				{/if}
				<div class="two">
					<button type="submit" class="btn primary">Add field</button>
					<button type="button" class="btn ghost" onclick={() => (adding = false)}>Cancel</button>
				</div>
			</form>
		{:else}
			<button type="button" class="btn ghost" onclick={() => (adding = true)}>Add a field</button>
		{/if}

		<h4>Always sent</h4>
		<p class="muted small">
			Only characters who appeared in the last turns are sent, to keep the prompt short. Pin the
			ones that must always be there.
		</p>
		<div class="chips">
			{#each status.pins as name (name)}
				<span class="chip"
					>{name}
					<button
						type="button"
						class="x"
						aria-label="Unpin {name}"
						onclick={() => extras.setPins(status.pins.filter((p) => p !== name))}>×</button
					></span
				>
			{/each}
		</div>
		<form class="setrow" onsubmit={addPin}>
			<input
				class="input"
				id="sf-pin"
				type="text"
				maxlength="120"
				bind:value={pin}
				placeholder="Pin a character"
				aria-label="Pin a character"
			/>
			<button type="submit" class="btn tiny">Pin</button>
		</form>

		<h4>Now</h4>
		{#if subjects.length === 0}
			<p class="muted small">
				Nothing yet. After a reply that opens with the block, what it said is kept here, and you can
				correct it.
			</p>
		{/if}
		{#each subjects as subject (subject.who)}
			<div class="who">{subject.who || 'Scene'}</div>
			{#each subject.lines as line (line.field.key)}
				{@const key = `${subject.who}\u0000${line.field.key}`}
				<div class="val">
					<span class="muted">{line.field.label}</span>
					{#if setting === key}
						<form
							class="setrow grow"
							onsubmit={(e) => {
								e.preventDefault();
								void commit(subject.who, line.field);
							}}
						>
							<input
								class="input"
								id="sv-{key}"
								type="text"
								bind:value={draft}
								aria-label="{line.field.label}, new value"
							/>
							<button type="submit" class="btn tiny primary">Set</button>
							<button type="button" class="btn tiny ghost" onclick={() => (setting = null)}
								>Cancel</button
							>
						</form>
					{:else}
						<span class="grow right"
							>{line.value}{#if line.byHand}<span class="note"> · by hand</span>{/if}</span
						>
						<button
							type="button"
							class="link"
							onclick={() => begin(subject.who, line.field, line.value)}>Edit</button
						>
					{/if}
				</div>
			{/each}
		{/each}
	{/if}
</div>

<style>
	.stack {
		display: grid;
		gap: 10px;
	}
	.small {
		font-size: 0.8rem;
	}
	h4 {
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--gold-text);
		font-weight: 600;
		margin-top: 6px;
	}
	.item {
		display: grid;
		gap: 8px;
		padding: 8px 10px;
		border-radius: var(--r-s);
		background: var(--surface);
		border: 1px solid var(--line);
	}
	.item.off .grow,
	.item.starter {
		opacity: 0.7;
	}
	.line {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.ic {
		width: 22px;
		text-align: center;
		color: var(--gold-text);
	}
	.grow {
		flex: 1;
		min-width: 0;
	}
	.right {
		text-align: right;
		overflow-wrap: anywhere;
	}
	.note {
		display: block;
		font-size: 0.72rem;
		color: var(--muted);
	}
	span.note.pad {
		align-self: end;
		padding-bottom: 10px;
	}
	.grow > .note {
		display: block;
	}
	.link {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--gold-text);
		font-weight: 600;
		font-size: 0.75rem;
		padding: 6px 8px;
		min-height: 32px;
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
		transition:
			transform 0.18s ease,
			background 0.18s ease;
	}
	.toggle[aria-checked='true'] {
		background: var(--gold);
		border-color: transparent;
	}
	.toggle[aria-checked='true']::after {
		transform: translateX(20px);
		background: var(--gold-ink);
	}
	.edit,
	.add {
		display: grid;
		gap: 10px;
	}
	.add {
		padding: 12px;
		border-radius: var(--r-s);
		background: var(--surface);
		border: 1px solid var(--line);
	}
	.two {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 8px;
	}
	.btn.tiny {
		min-height: 34px;
		padding: 4px 12px;
		font-size: 0.8rem;
	}
	.btn.danger {
		color: var(--danger);
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 4px 6px 4px 12px;
		border-radius: var(--r-pill);
		background: var(--gold-soft);
		border: 1px solid var(--line);
		font-size: 0.8rem;
	}
	.x {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--muted);
		font-size: 1rem;
		min-width: 28px;
		min-height: 28px;
	}
	.setrow {
		display: flex;
		gap: 6px;
		align-items: center;
	}
	.who {
		font-weight: 600;
		margin-top: 4px;
	}
	.val {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 4px 2px;
		border-bottom: 1px solid var(--line);
		font-size: 0.88rem;
	}
</style>
