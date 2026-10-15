<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import AppBar from '#lib/AppBar.svelte';
	import { api, ApiError, type Defaults, type Entry, type StatusStarter } from '#lib/api.ts';
	import { blurb } from '#lib/library.ts';
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
	/** The shipped status fields, offered unticked: a story has none until the reader asks. */
	let starters = $state<StatusStarter[]>([]);
	let ticked = $state<string[]>([]);

	const character = $derived(characters?.find((c) => c.id === characterId) ?? null);
	const ready = $derived(characterId !== null && name.trim().length > 0 && !busy);
	/** The note of the persona that will play: the picked one, or the default when none is. */
	const personaNote = $derived(
		(
			personas.find((p) => p.id === (personaId || defaults?.default_persona_id))?.description ?? ''
		).trim()
	);

	onMount(async () => {
		try {
			[characters, personas, defaults] = await Promise.all([
				api.characters(),
				api.personas(),
				api.defaults()
			]);
			if (characters.length === 1) characterId = characters[0].id;
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
		if (!name.trim())
			name = `${entry.name}, ${new Date().toLocaleDateString(undefined, { month: 'long', day: 'numeric' })}`;
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
						'Add them in the story’s settings, on the Status tab.'
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
							<span class="who">{entry.name.charAt(0).toUpperCase()}</span>
							<span class="text">
								<b>{entry.name}</b>
								<small class:prose={!blurb(entry).note}>{blurb(entry).text}</small>
							</span>
						</button>
					{/each}
				</div>
			{/if}
		</section>
		<section>
			<h2>Who you are</h2>
			<label class="field">
				<span>Persona</span>
				<select class="input" id="persona" bind:value={personaId}>
					<option value="">
						{defaults?.default_persona_name
							? `Default: ${defaults.default_persona_name}`
							: 'Nobody in particular'}
					</option>
					{#each personas as persona (persona.id)}
						<option value={persona.id}>{persona.name}</option>
					{/each}
				</select>
			</label>
			{#if personaNote}<p class="muted note">{personaNote}</p>{/if}
			<a class="build" href="/library/personas/from-pieces?then=new"
				>Build a new persona from pieces</a
			>
		</section>
		{#if starters.length > 0}
			<section>
				<h2>Status block</h2>
				<p class="muted note">
					Lines the model writes at the top of each reply, and the app keeps. Change them any time
					in the story’s settings.
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
		<section>
			<h2>Call it</h2>
			<label class="field">
				<span>Story name</span>
				<input
					class="input"
					id="story-name"
					type="text"
					bind:value={name}
					maxlength="200"
					placeholder="First night at the Heron"
					required
				/>
			</label>
		</section>
		<div class="foot">
			<button class="btn primary" type="submit" disabled={!ready}>
				{busy ? 'Starting…' : character ? `Start with ${character.name}` : 'Start'}
			</button>
		</div>
	</form>
</div>

<style>
	.screen {
		min-height: 100%;
		display: flex;
		flex-direction: column;
	}
	form {
		flex: 1;
		display: grid;
		gap: 24px;
		align-content: start;
		padding: 16px 16px calc(24px + var(--safe-bottom));
		max-width: 640px;
		width: 100%;
		margin: 0 auto;
	}
	section {
		display: grid;
		gap: 10px;
	}
	h2 {
		font-size: 0.8rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--gold-text);
	}
	.cards {
		display: grid;
		gap: 8px;
	}
	.card {
		display: grid;
		grid-template-columns: 44px 1fr;
		gap: 12px;
		align-items: center;
		text-align: left;
		padding: 12px;
		border-radius: var(--r-m);
		background: var(--surface);
		border: 1px solid var(--line);
	}
	.card[aria-checked='true'] {
		border-color: var(--gold);
		box-shadow: 0 0 0 3px var(--gold-soft);
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
	.text small {
		color: var(--fg-2);
		font-size: 0.85rem;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
	.build {
		justify-self: start;
		font-size: 0.85rem;
		font-weight: 600;
		text-decoration: none;
		color: var(--gold-text);
		padding: 6px 0;
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
		display: grid;
	}
</style>
