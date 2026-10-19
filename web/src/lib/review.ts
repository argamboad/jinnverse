/**
 * The fact review's proposals as the sheet works them: each kept until the reader drops it, and
 * the kept ones sent back as the confirmed set. Pure, so the choices are testable without a
 * screen.
 */

import type { Proposal } from './api.ts';

export type Confirmed = {
	action: Proposal['action'];
	fact_ids: string[];
	subject?: string;
	text?: string;
};

/** What goes back to the API: the kept proposals, by their facts' ids. */
export function confirmed(proposals: Proposal[], kept: boolean[]): Confirmed[] {
	return proposals
		.filter((_, i) => kept[i])
		.map((p) => ({
			action: p.action,
			fact_ids: p.facts.map((f) => f.id),
			...(p.subject ? { subject: p.subject } : {}),
			...(p.text ? { text: p.text } : {})
		}));
}

/** Whose the new sentence is: the proposal says, or the first fact it touches. */
export function subjectOf(p: Proposal): string {
	return p.subject ?? p.facts[0]?.subject ?? '';
}

/** "11 of 12 on", the sheet's footer. */
export function tally(kept: boolean[]): string {
	const on = kept.filter(Boolean).length;
	return `${on} of ${kept.length} on`;
}

/** What a condense's confirm says it would do, from the dry run. */
export function condensePlan(plan: {
	summaries: number;
	from_sequence: number | null;
	to_sequence: number | null;
	tokens_before: number;
}): string {
	const turns =
		plan.from_sequence !== null && plan.to_sequence !== null
			? `turns ${plan.from_sequence}–${plan.to_sequence}, `
			: '';
	return `${plan.summaries} summaries — ${turns}about ${plan.tokens_before.toLocaleString()} tokens of every reply — become one account.`;
}
