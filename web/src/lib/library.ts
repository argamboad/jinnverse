/** The library's small rules that need no screen: the note a list shows, the count beside "show
 * hidden", and how much of a description is left. */

import type { Entry, Piece, Shelf, Voice } from './api.ts';

/** The most a description may hold; the API refuses more. */
export const DESCRIPTION_LENGTH = 200;

/** What a list shows under a name: the owner's note when there is one, the start of the text
 * otherwise. `note` says which, so the text is set in the prose face and the note is not. */
export function blurb(entry: Pick<Entry, 'description' | 'preview'>): {
	text: string;
	note: boolean;
} {
	const note = entry.description?.trim();
	return note ? { text: note, note: true } : { text: entry.preview, note: false };
}

/** The same for a piece of a persona: its description, or the start of its text. */
export function pieceBlurb(piece: Pick<Piece, 'description' | 'text'>): {
	text: string;
	note: boolean;
} {
	return blurb({
		description: piece.description,
		preview: piece.text.slice(0, DESCRIPTION_LENGTH)
	});
}

/** The count of hidden `_name` entries, as it reads beside the toggle; nothing when there are none. */
export function hiddenCount(hidden: number | undefined): string {
	return hidden ? ` (${hidden})` : '';
}

/** How many characters of a description can still be typed (negative once over the limit). */
export function remaining(description: string): number {
	return DESCRIPTION_LENGTH - description.length;
}

/** A description as it is sent: trimmed, and blank is none, which clears it. */
export function sentDescription(description: string): string | null {
	return description.trim() || null;
}

/** The small line under an entry: its version, and for a character or a persona how many
 * stories use it. A snippet is copied when used, so it says only its version. */
export function entryMeta(entry: Pick<Entry, 'version' | 'used'>, shelf: Shelf): string {
	if (shelf === 'snippets') return `v${entry.version}`;
	const use =
		entry.used === 0 ? 'unused' : `in ${entry.used} ${entry.used === 1 ? 'story' : 'stories'}`;
	return `v${entry.version} · ${use}`;
}

const VOICES: Voice[] = ['he', 'she', 'they', 'any'];

/** What the pool of pieces holds, in one line: how many, across how many slots, and by voice
 * (a voice with none is left out). */
export function piecesSummary(pieces: Pick<Piece, 'slot' | 'voice'>[]): string {
	if (pieces.length === 0) return 'No pieces yet';
	const slots = new Set(pieces.map((p) => p.slot)).size;
	const voices = VOICES.map((v) => [v, pieces.filter((p) => p.voice === v).length] as const)
		.filter(([, n]) => n > 0)
		.map(([v, n]) => `${v} ${n}`);
	const head = `${pieces.length} ${pieces.length === 1 ? 'piece' : 'pieces'} across ${slots} ${slots === 1 ? 'slot' : 'slots'}`;
	return [head, ...voices].join(' · ');
}
