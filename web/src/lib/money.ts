/** A cost from the API (a decimal string) as a screen shows it: "—" when unknown, "<$0.01" for a
 * sliver, whole dollars with cents otherwise. */
export function money(cost: string | undefined | null): string {
	if (cost === undefined || cost === null) return '—';
	const n = Number(cost);
	if (n === 0) return '$0';
	return n < 0.01 ? '<$0.01' : `$${n.toFixed(2)}`;
}
