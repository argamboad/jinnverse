/** The persona builder's rules that need no screen: what a persona is not made without, and the
 * small changes a pick goes through. The join itself is the server's (`/persona-pieces/preview`),
 * so the client never disagrees with it about what a persona looks like. */

import type { Picks, Slot, Voice } from './api.ts';

export const VOICES: { id: Voice; label: string }[] = [
	{ id: 'he', label: 'He' },
	{ id: 'she', label: 'She' },
	{ id: 'they', label: 'They' }
];

/** The voices a piece may be written in: the three a persona has, and `any` for a piece with no
 * pronouns in it, which a persona of any voice may use. */
export const PIECE_VOICES: { id: Voice; label: string }[] = [
	...VOICES,
	{ id: 'any', label: 'Any' }
];

/** The slots a persona is not made without, as the screens ask (the API itself only needs one
 * piece): every persona opens with its name and its look, and a piece that writes the name needs
 * a name piece. Every other slot is optional. */
export const NEEDED: Record<string, string> = {
	name: 'a name',
	look: 'an identity and look'
};

export function isNeeded(slot: string): boolean {
	return slot in NEEDED;
}

/** What the pick still lacks, in the order a persona opens with it. */
export function missing(picks: Picks): string[] {
	return Object.entries(NEEDED)
		.filter(([slot]) => !(picks[slot]?.length ?? 0))
		.map(([, wanted]) => wanted);
}

/** The sentence that says so, or null when nothing is missing. */
export function missingSentence(picks: Picks): string | null {
	const lacks = missing(picks);
	if (!lacks.length) return null;
	return `A persona needs ${lacks.join(' and ')}: pick ${lacks.length > 1 ? 'them' : 'it'} first.`;
}

/** The pick with a piece added, or taken back if it was there. Never changes the one it is given. */
export function toggled(picks: Picks, slot: string, id: string): Picks {
	const current = picks[slot] ?? [];
	const next = current.includes(id) ? current.filter((i) => i !== id) : [...current, id];
	const rest = Object.fromEntries(Object.entries(picks).filter(([key]) => key !== slot));
	return next.length ? { ...rest, [slot]: next } : rest;
}

/** The pick limited to the pieces still in the pool, empty slots dropped: after a change of voice,
 * a piece written in the other one is put back. */
export function keeping(picks: Picks, known: Set<string>): Picks {
	const kept: Picks = {};
	for (const [slot, ids] of Object.entries(picks)) {
		const stay = ids.filter((id) => known.has(id));
		if (stay.length) kept[slot] = stay;
	}
	return kept;
}

/** Whether the pick has anything to join: a name alone is not a persona, and the server says so
 * with a 422, which is no use asking for on every change. */
export function hasText(picks: Picks): boolean {
	return Object.entries(picks).some(([slot, ids]) => slot !== 'name' && ids.length > 0);
}

export function count(picks: Picks): number {
	return Object.values(picks).reduce((n, ids) => n + ids.length, 0);
}

/** A row of the builder's checklist: one slot, or the slots that write one paragraph together
 * (home, vehicle and pets). */
export interface SlotGroup {
	key: string;
	label: string;
	slots: Slot[];
}

/** The slots as the checklist shows them, in order: slots that share a paragraph share a row. */
export function groupSlots(slots: Slot[]): SlotGroup[] {
	const groups: SlotGroup[] = [];
	for (const slot of slots) {
		const last = groups.at(-1);
		if (slot.paragraph !== null && last && last.slots[0].paragraph === slot.paragraph) {
			last.slots.push(slot);
			last.key = `${last.key}+${slot.key}`;
			last.label = `${last.label} · ${slot.label}`;
		} else {
			groups.push({ key: slot.key, label: slot.label, slots: [slot] });
		}
	}
	return groups;
}

/** The line under the builder's title: how many slots are picked, and what is still needed. */
export function builderLine(slots: Slot[], picks: Picks): string {
	const picked = slots.filter((s) => picks[s.key]?.length).length;
	const needed = missing(picks).length;
	return `${picked} of ${slots.length} slots picked${needed ? ` · ${needed} needed` : ''}`;
}

/** What a checklist row says when nothing is picked in it: a needed slot asks, an optional one
 * may be left, and a shared row says how many pieces it takes. */
export function rowHint(group: SlotGroup): string {
	if (group.slots.length > 1) return `One paragraph, up to ${group.slots.length} pieces`;
	return group.slots.some((s) => isNeeded(s.key)) ? 'Pick one' : 'Pick one, or leave it';
}

/** One piece for the slot, chosen by `roll` (a number in [0, 1)); null when the slot has none. */
export function randomFor(ids: string[], roll: number): string | null {
	return ids.length ? ids[Math.min(ids.length - 1, Math.floor(roll * ids.length))] : null;
}
