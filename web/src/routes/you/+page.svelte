<script lang="ts">
	import { onMount } from 'svelte';
	import AppBar from '#lib/AppBar.svelte';
	import Tabs from '#lib/Tabs.svelte';
	import ThemeSwitch from '#lib/ThemeSwitch.svelte';
	import { api, API_URL, token, type SpendReport } from '#lib/api.ts';
	import { server } from '#lib/health.svelte.ts';
	import { money } from '#lib/money.ts';
	import { session } from '#lib/session.svelte.ts';
	import { apiHost, monthStart, tokenName } from '#lib/you.ts';

	const name = tokenName(token.get()) ?? 'reader';

	/** This month's spend, from the first of the month; null until it is read, or if it cannot be. */
	let month = $state<SpendReport | null>(null);
	let byStory = $state(false);

	onMount(() => {
		api
			.spend(monthStart())
			.then((report) => (month = report))
			.catch(() => undefined); // the card says "—" and the rest of the screen still works
	});
</script>

<div class="screen">
	<AppBar title="You" mark />
	<main>
		<section class="card account">
			<span class="avatar" aria-hidden="true">{name.charAt(0).toUpperCase()}</span>
			<span class="who">
				<b>{name}</b>
				<span class="muted">Signed in on this device · token lasts a month</span>
			</span>
			<button class="btn ghost small" type="button" onclick={() => session.signOut()}
				>Sign out</button
			>
		</section>
		<section class="card">
			<div class="head">
				<h2>This month</h2>
				<span class="mono total">{money(month?.cost)}</span>
			</div>
			<div class="grid">
				<span>Calls</span><b>{month?.calls ?? '—'}</b>
				<span>Rerolled away</span><b class="warn">{money(month?.discarded_cost)}</b>
				{#if month && month.cached_share !== null}
					<span>Cached share</span><b>{Math.round(month.cached_share * 100)}%</b>
				{/if}
			</div>
			{#if month && month.by_story.length > 0}
				<button
					class="link"
					type="button"
					aria-expanded={byStory}
					onclick={() => (byStory = !byStory)}>By story {byStory ? '⌄' : '›'}</button
				>
				{#if byStory}
					<ul class="stories">
						{#each month.by_story as s (s.story_id)}
							<li>
								<span>{s.name}</span>
								<span class="mono"
									>{money(s.cost)} · {s.calls} {s.calls === 1 ? 'call' : 'calls'}</span
								>
							</li>
						{/each}
					</ul>
				{/if}
			{/if}
		</section>
		<section class="card">
			<h2>Theme</h2>
			<ThemeSwitch />
		</section>
		<p class="foot muted">
			API <code>{apiHost(API_URL)}</code>{#if server.commit}
				· build <code>{server.commit.slice(0, 7)}</code>{/if}
		</p>
	</main>
	<Tabs />
</div>

<style>
	.screen {
		min-height: 100%;
		display: flex;
		flex-direction: column;
	}
	main {
		flex: 1;
		padding: 16px 16px 24px;
		display: grid;
		gap: 12px;
		align-content: start;
		max-width: 640px;
		width: 100%;
		margin: 0 auto;
	}
	.card {
		background: var(--surface);
		border: 1px solid var(--line);
		border-radius: var(--r-m);
		padding: 16px;
		display: grid;
		gap: 10px;
		justify-items: start;
	}
	.account {
		grid-template-columns: 44px 1fr auto;
		gap: 12px;
		align-items: center;
		justify-items: stretch;
	}
	.avatar {
		width: 44px;
		height: 44px;
		border-radius: 50%;
		background: var(--gold-soft);
		color: var(--gold-text);
		display: grid;
		place-items: center;
		font-weight: 600;
	}
	.who {
		display: grid;
		min-width: 0;
	}
	.who .muted {
		font-size: 0.82rem;
	}
	.btn.small {
		min-height: 36px;
		padding: 0 14px;
		font-size: 0.85rem;
	}
	h2 {
		font-size: 1rem;
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		width: 100%;
	}
	.total {
		font-size: 1.1rem;
	}
	.grid {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 4px 12px;
		width: 100%;
		font-size: 0.88rem;
		color: var(--fg-2);
		font-variant-numeric: tabular-nums;
	}
	.grid b {
		font-weight: 600;
		color: var(--fg);
	}
	.grid .warn {
		color: var(--warn);
	}
	.link {
		appearance: none;
		border: 0;
		background: transparent;
		padding: 4px 0;
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--gold-text);
	}
	.stories {
		list-style: none;
		margin: 0;
		padding: 0;
		width: 100%;
		display: grid;
		gap: 6px;
		font-size: 0.85rem;
		color: var(--fg-2);
	}
	.stories li {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		border-top: 1px solid var(--line);
		padding-top: 6px;
	}
	.stories li span:first-child {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.stories .mono {
		white-space: nowrap;
	}
	.foot {
		font-size: 0.78rem;
		padding: 4px 6px;
	}
</style>
