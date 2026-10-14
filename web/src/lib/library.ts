/** The library's small rules that need no screen: the note a list shows, the count beside "show
 * hidden", and how much of a description is left. */

import type { Entry, Piece } from './api.ts';

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
