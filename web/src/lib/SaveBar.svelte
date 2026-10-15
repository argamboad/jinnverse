<script lang="ts">
	/** The bar under a document editor while it has unsaved changes: what is pending, Discard and
	 * Save. A document (a card, a persona, a snippet, a piece) saves only from here; settings save
	 * as they are touched and have no bar. */
	let {
		note,
		saveLabel,
		busy = false,
		disabled = false,
		onsave,
		ondiscard
	}: {
		note: string;
		saveLabel: string;
		busy?: boolean;
		disabled?: boolean;
		onsave: () => void;
		ondiscard: () => void;
	} = $props();
</script>

<div class="bar" role="region" aria-label="Unsaved changes">
	<span class="note">{note}</span>
	<button type="button" class="btn ghost" onclick={ondiscard} disabled={busy}>Discard</button>
	<button type="button" class="btn primary" onclick={onsave} disabled={busy || disabled}
		>{busy ? 'Saving…' : saveLabel}</button
	>
</div>

<style>
	.bar {
		flex: none;
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 10px 16px calc(14px + var(--safe-bottom));
		border-top: 1px solid var(--gold);
		background: var(--surface);
	}
	.note {
		flex: 1;
		min-width: 0;
		font-size: 0.85rem;
		color: var(--fg-2);
	}
	.btn {
		min-height: 40px;
		padding: 8px 16px;
		font-size: 0.9rem;
		white-space: nowrap;
	}
	@media (min-width: 900px) {
		.bar {
			padding-inline: 24px;
		}
	}
</style>
