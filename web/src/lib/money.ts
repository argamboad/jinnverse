/** A cost from the API (a decimal string) as a screen shows it: "—" when unknown, "<$0.01" for a
 * sliver, whole dollars with cents otherwise. */
export function money(cost: string | undefined | null): string {
	if (cost === undefined || cost === null) return '—';
	const n = Number(cost);
	if (n === 0) return '$0';
	return n < 0.01 ? '<$0.01' : `$${n.toFixed(2)}`;
}

/** A cost too small for cents, shown to the tenth of a cent — what one call costs. A review of
 * fifty facts is $0.003, and "<$0.01" would not say whether to press it. */
export function fine(cost: string | undefined | null): string {
	if (cost === undefined || cost === null) return '—';
	const n = Number(cost);
	return n < 0.01 ? `$${n.toFixed(4)}` : money(cost);
}
