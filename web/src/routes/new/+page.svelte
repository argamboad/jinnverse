<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import AppBar from '#lib/AppBar.svelte';
	import { api, ApiError, type Defaults, type Entry, type StatusStarter } from '#lib/api.ts';
	import { blurb } from '#lib/library.ts';
	import Prose from '#lib/Prose.svelte';
	import { scopeNote } from '#lib/status.ts';
	import { stories } from '#lib/stories.svelte.ts';
	import { toasts } from '#lib/toasts.svelte.ts';

	let characters = $state<Entry[] | null>(null);
	let personas = $state<Entry[]>([]);
	let defaults = $state<Defaults | null>(null);
	let characterId = $state<string | null>(null);
	let personaId = $state<string>(''); // '' means the default persona
	let name = $state('');
	let busy = $state(false);
	/** What each picked character opens on, read once when it is first picked. */
	let openings = $state<Record<string, string | null>>({});
	/** The shipped status fields, offered unticked: a story has none until the reader asks. */
	let starters = $state<StatusStarter[]>([]);
	let ticked = $state<string[]>([]);
	/** The opening shows its first lines; this lets the rest out. */
	let wholeOpening = $state(false);

	const character = $derived(characters?.find((c) => c.id === characterId) ?? null);
	const opening = $derived(characterId ? (openings[characterId] ?? null) : null);
	/** The persona that will play: the picked one, or the default when none is. */
	const playing = $derived(
		personas.find((p) => p.id === (personaId || defaults?.default_persona_id)) ?? null
	);
	/** The default persona is the first row; the rest follow in the library's order. */
	const defaultPersona = $derived(
		personas.find((p) => p.id === defaults?.default_persona_id) ?? null
	);
	const others = $derived(personas.filter((p) => p.id !== defaults?.default_persona_id));
	const ready = $derived(characterId !== null && name.trim().length > 0 && !busy);

	onMount(async () => {
		try {
			[characters, personas, defaults] = await Promise.all([
				api.characters(),
				api.personas(),
				api.defaults()
			]);
			if (characters.length === 1) pick(characters[0]);
			// Back from building a persona: it is the one picked.
			const built = page.url.searchParams.get('persona');
			if (built && personas.some((p) => p.id === built)) personaId = built;
			api
				.statusStarters()
				.then((found) => (starters = found))
				.catch(() => undefined); // the section simply does not appear
		} catch (error) {
			toasts.show(
				'danger',
				'Could not read the library',
				error instanceof Error ? error.message : undefined
			);
		}
	});

	function pick(entry: Entry) {
		characterId = entry.id;
		wholeOpening = false;
		if (!name.trim())
			name = `${entry.name}, ${new Date().toLocaleDateString(undefined, { month: 'long', day: 'numeric' })}`;
		if (!(entry.id in openings)) {
			api
				.entry('characters', entry.id)
				.then((full) => (openings[entry.id] = full.opening?.trim() || null))
				.catch(() => (openings[entry.id] = null));
		}
	}

	async function create(event: SubmitEvent) {
		event.preventDefault();
		if (!ready || characterId === null) return;
		busy = true;
		try {
			const story = await api.createStory({
				name: name.trim(),
				character_id: characterId,
				persona_id: personaId || null
			});
			stories.touch(story);
			if (ticked.length > 0) {
				try {
					await api.adoptStatus(story.id, ticked);
				} catch {
					toasts.show(
						'info',
						'The story started without its status lines',
						'Add them from the story’s Dials, on the Status tab.'
					);
				}
			}
			await goto(`/story/${story.id}`);
		} catch (error) {
			toasts.show(
				'danger',
				'Could not start the story',
				error instanceof ApiError ? error.message : undefined
			);
		} finally {
			busy = false;
		}
	}
</script>

<div class="screen">
	<AppBar title="New story" back="/" />
	<form onsubmit={create}>
		<div class="fields">
			<section>
				<h2>Who with</h2>
				{#if characters === null}
					<p class="muted">Reading the library…</p>
				{:else if characters.length === 0}
					<p class="muted">The library has no characters yet. Add one in the library first.</p>
				{:else}
					<div class="cards" role="radiogroup" aria-label="Character">
						{#each characters as entry (entry.id)}
							<button
								type="button"
								class="card"
								role="radio"
								aria-checked={characterId === entry.id}
								onclick={() => pick(entry)}
							>
								<span class="tile">{entry.name.charAt(0).toUpperCase()}</span>
								<span class="text">
									<b>{entry.name}</b>
									<small class:prose={!blurb(entry).note}>{blurb(entry).text}</small>
								</span>
							</button>
						{/each}
					</div>
					{#if opening}
						<div class="opens">
							<span class="eyebrow-line">Opens on</span>
							<div class="text-clip" class:whole={wholeOpening}>
								<Prose text={opening} />
							</div>
							<button type="button" class="more" onclick={() => (wholeOpening = !wholeOpening)}
								>{wholeOpening ? 'Show less' : 'Show all'}</button
							>
						</div>
					{/if}
				{/if}
			</section>
			<section>
				<h2>As</h2>
				<div class="rows" role="radiogroup" aria-label="Persona">
					{#if defaultPersona}
						{@render row(defaultPersona, '', true)}
					{:else}
						<button
							type="button"
							class="row"
							role="radio"
							aria-checked={personaId === ''}
							onclick={() => (personaId = '')}
						>
							<span class="tile small">·</span>
							<span class="text"><b>Nobody in particular</b></span>
						</button>
					{/if}
					{#each others as persona (persona.id)}
						{@render row(persona, persona.id, false)}
					{/each}
				</div>
			</section>
			<section>
				<h2>Called</h2>
				<input
					class="input"
					id="story-name"
					type="text"
					aria-label="Story name"
					bind:value={name}
					maxlength="200"
					placeholder="First night at the Heron"
					required
				/>
				<small class="muted">You can rename it any time from the story’s title.</small>
			</section>
			{#if starters.length > 0}
				<section>
					<h2>Status block</h2>
					<p class="muted note">
						Lines the model writes at the top of each reply, and the app keeps. Change them any time
						from the story’s Dials, on the Status tab.
					</p>
					<div class="ticks">
						{#each starters as starter (starter.key)}
							<label class="tick">
								<input type="checkbox" bind:group={ticked} value={starter.key} />
								<span class="ic" aria-hidden="true">{starter.icon ?? '·'}</span>
								<span class="grow">
									<b>{starter.label}</b>
									<small>{scopeNote(starter)}</small>
								</span>
							</label>
						{/each}
					</div>
				</section>
			{/if}
		</div>
		<div class="foot">
			<button class="btn primary" type="submit" disabled={!ready}>
				{busy
					? 'Starting…'
					: character
						? `Start with ${character.name}${playing ? ` as ${playing.name}` : ''}`
						: 'Start'}
			</button>
		</div>
	</form>
</div>

{#snippet row(persona: Entry, value: string, isDefault: boolean)}
	<button
		type="button"
		class="row"
		role="radio"
		aria-checked={personaId === value}
		onclick={() => (personaId = value)}
	>
		<span class="tile small">{persona.name.charAt(0).toUpperCase()}</span>
		<span class="text">
			<b>{persona.name}</b>
			<small class:prose={!blurb(persona).note}>{blurb(persona).text}</small>
		</span>
		{#if isDefault}<span class="chip gold">default</span>{/if}
	</button>
{/snippet}

<style>
	.screen {
		height: 100%;
		display: flex;
		flex-direction: column;
	}
	form {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		max-width: 640px;
		width: 100%;
		margin: 0 auto;
	}
	/* Only the strip of cards scrolls sideways; the form scrolls up and down. */
	.fields {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		overflow-x: hidden;
		display: grid;
		gap: 22px;
		align-content: start;
		padding: 16px 16px 24px;
	}
	section {
		display: grid;
		gap: 10px;
		min-width: 0;
	}
	h2 {
		font-size: 0.8rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--gold-text);
		font-weight: 600;
	}
	.cards {
		display: flex;
		gap: 8px;
		overflow-x: auto;
		scrollbar-width: none;
		min-width: 0;
		padding: 4px 2px;
	}
	.card {
		appearance: none;
		flex: none;
		width: 132px;
		display: grid;
		gap: 8px;
		align-content: start;
		text-align: left;
		padding: 12px;
		border-radius: var(--r-m);
		background: var(--surface);
		border: 1px solid var(--line);
	}
	.card[aria-checked='true'],
	.row[aria-checked='true'] {
		border-color: var(--gold);
		box-shadow: 0 0 0 3px var(--gold-soft);
	}
	.tile {
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
	.tile.small {
		width: 36px;
		height: 36px;
		border-radius: 10px;
		font-size: 1.1rem;
	}
	.card[aria-checked='true'] .tile,
	.row[aria-checked='true'] .tile {
		background: var(--gold-soft);
	}
	.text {
		min-width: 0;
		display: grid;
		gap: 2px;
	}
	.card .text b {
		font-size: 0.95rem;
		font-weight: 600;
	}
	.card .text small {
		color: var(--fg-2);
		font-size: 0.78rem;
		line-height: 1.3;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.opens {
		display: grid;
		gap: 4px;
		padding: 0 2px;
		justify-items: start;
	}
	.text-clip {
		--prose-size: 0.9rem;
		--prose-leading: 1.5;
		color: var(--fg-2);
		max-height: 6.8rem;
		overflow: hidden;
		-webkit-mask-image: linear-gradient(to bottom, #000 70%, transparent);
		mask-image: linear-gradient(to bottom, #000 70%, transparent);
	}
	.text-clip.whole {
		max-height: none;
		-webkit-mask-image: none;
		mask-image: none;
	}
	.eyebrow-line {
		font-size: 0.72rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--muted);
		font-weight: 600;
	}
	.more {
		appearance: none;
		border: 0;
		background: transparent;
		color: var(--gold-text);
		font-weight: 600;
		font-size: 0.8rem;
		padding: 4px 0;
	}
	.rows {
		display: grid;
		gap: 8px;
	}
	.row {
		appearance: none;
		display: grid;
		grid-template-columns: 36px 1fr auto;
		gap: 12px;
		align-items: center;
		text-align: left;
		padding: 10px 12px;
		border-radius: 14px;
		background: var(--surface);
		border: 1px solid var(--line);
		color: inherit;
		text-decoration: none;
	}
	.row .text small {
		color: var(--fg-2);
		font-size: 0.82rem;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	small.muted {
		font-size: 0.74rem;
	}
	.ticks {
		display: grid;
		gap: 6px;
	}
	.tick {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 10px 12px;
		border-radius: var(--r-s);
		background: var(--surface);
		border: 1px solid var(--line);
		min-height: 48px;
	}
	.tick input {
		accent-color: var(--gold);
		width: 20px;
		height: 20px;
		flex: none;
	}
	.tick .ic {
		width: 22px;
		text-align: center;
		color: var(--gold-text);
	}
	.tick .grow {
		display: grid;
		gap: 1px;
	}
	.tick small {
		color: var(--muted);
		font-size: 0.75rem;
	}
	.foot {
		flex: none;
		display: grid;
		padding: 10px 16px calc(14px + var(--safe-bottom));
		border-top: 1px solid var(--line);
		background: var(--bg);
	}
	.foot .btn {
		min-height: 48px;
	}
</style>
