/** The status block's small rules that need no screen: how a field is described, how the values
 * are grouped by who they belong to, and which characters are in scene. */

import type { Status, StatusField, StatusValue } from './api.ts';

/** A character whose block was written within this many messages of the newest is in scene.
 * The same number the API uses when it builds the prompt. */
export const RECENT_TURNS = 12;
/** The most characters shown, as the API sends at most so many. */
export const MOST_CHARACTERS = 12;

/** What a field belongs to, in a few words: `Scene`, `Each character · words`. */
export function scopeNote(field: Pick<StatusField, 'scope' | 'kind'>): string {
	const who = field.scope === 'scene' ? 'Scene' : 'Each character';
	return field.kind === 'words' ? `${who} · words` : who;
}

/** The words of a word field as typed (`Guarded, Teasing`), without blanks or repeats. */
export function parseWords(typed: string): string[] {
	const seen = new Map<string, string>();
	for (const part of typed.split(/[,|;\n]/)) {
		const word = part.trim();
		if (word && !seen.has(word.toLowerCase())) seen.set(word.toLowerCase(), word);
	}
	return [...seen.values()];
}

export interface Line {
	field: StatusField;
	value: string;
	byHand: boolean;
}

export interface Subject {
	/** Empty for the scene. */
	who: string;
	lines: Line[];
}

/** The values of the story's fields: the scene first, then each character, in the order the
 * fields are listed. A value whose field no longer exists is left out. */
export function grouped(status: Pick<Status, 'fields' | 'values'>): Subject[] {
	const fields = new Map(status.fields.map((f) => [f.key, f]));
	const bySubject = new Map<string, Line[]>();
	for (const v of status.values) {
		const field = fields.get(v.field);
		if (!field) continue;
		const lines = bySubject.get(v.who) ?? [];
		lines.push({ field, value: v.value, byHand: v.by_hand });
		bySubject.set(v.who, lines);
	}
	const rank = (line: Line) => line.field.position;
	const subjects = [...bySubject].map(([who, lines]) => ({
		who,
		lines: lines.sort((a, b) => rank(a) - rank(b))
	}));
	return [
		...subjects.filter((s) => s.who === ''),
		...subjects.filter((s) => s.who !== '').sort((a, b) => a.who.localeCompare(b.who))
	];
}

/** The scene's lines for the strip under the app bar: only fields that are on. */
export function sceneLines(status: Pick<Status, 'fields' | 'values'>): Line[] {
	return (grouped(status).find((s) => s.who === '')?.lines ?? []).filter((l) => l.field.enabled);
}

/** The characters to show as chips: pinned ones first, then those who wrote a line within
 * `RECENT_TURNS` of `newest`, most recent first, as the API chooses who it sends. */
export function inScene(
	status: Pick<Status, 'fields' | 'values' | 'pins'>,
	newest: number
): { who: string; pinned: boolean }[] {
	const keys = new Set(status.fields.filter((f) => f.scope === 'character').map((f) => f.key));
	const last = new Map<string, { who: string; seen: number }>();
	for (const v of status.values as StatusValue[]) {
		if (!v.who || !keys.has(v.field)) continue;
		const k = v.who.trim().toLowerCase();
		const known = last.get(k);
		last.set(k, { who: known?.who ?? v.who, seen: Math.max(known?.seen ?? 0, v.seen ?? 0) });
	}
	const pinned = status.pins
		.map((p) => last.get(p.trim().toLowerCase()) ?? null)
		.filter((x): x is { who: string; seen: number } => x !== null);
	const taken = new Set(pinned.map((p) => p.who));
	const recent = [...last.values()]
		.filter((c) => !taken.has(c.who) && c.seen >= newest - RECENT_TURNS)
		.sort((a, b) => b.seen - a.seen || a.who.localeCompare(b.who));
	return [
		...pinned.map((p) => ({ who: p.who, pinned: true })),
		...recent.map((r) => ({ who: r.who, pinned: false }))
	].slice(0, MOST_CHARACTERS);
}
