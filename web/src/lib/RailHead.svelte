<script lang="ts">
	import Lamp from '#lib/Lamp.svelte';

	/** The top of a wide screen's left rail: the mark, the Stories / Library switch, and You. */
	let { section }: { section: 'stories' | 'library' } = $props();
</script>

<div class="head">
	<Lamp size={30} />
	<nav class="seg" aria-label="Sections">
		<a
			href="/"
			class:on={section === 'stories'}
			aria-current={section === 'stories' ? 'page' : undefined}>Stories</a
		>
		<a
			href="/library"
			class:on={section === 'library'}
			aria-current={section === 'library' ? 'page' : undefined}>Library</a
		>
	</nav>
	<div class="grow"></div>
	<a class="avatar" href="/you" aria-label="You">R</a>
</div>

<style>
	.head {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 12px 12px 8px;
		min-height: 62px;
	}
	.grow {
		flex: 1;
	}
	.seg {
		display: flex;
		gap: 2px;
		padding: 3px;
		border-radius: var(--r-pill);
		background: var(--surface-2);
		border: 1px solid var(--line);
	}
	.seg a {
		text-decoration: none;
		color: var(--fg-2);
		font-weight: 500;
		font-size: 0.85rem;
		padding: 5px 12px;
		border-radius: var(--r-pill);
	}
	.seg a.on {
		background: var(--gold);
		color: var(--gold-ink);
	}
	.avatar {
		width: 32px;
		height: 32px;
		border-radius: 50%;
		background: var(--gold-soft);
		color: var(--gold-text);
		display: grid;
		place-items: center;
		font-weight: 600;
		font-size: 0.8rem;
		text-decoration: none;
	}
</style>
