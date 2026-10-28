/** The library's small rules that need no screen: the note a list shows, the count beside "show
 * hidden", and how much of a description is left. */

import type { Entry, Shelf } from './api.ts';

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

/** What the save bar says beside its buttons while an entry has unsaved changes: on a wide
 * window, which version the stories using it will read, and when. */
export function saveNote(one: string, used: number, next: number, wide: boolean): string {
	if (!wide || used === 0) return 'Unsaved changes';
	return used === 1
		? `Unsaved changes · the story using this ${one} reads v${next} from its next turn`
		: `Unsaved changes · the ${used} stories using this ${one} read v${next} from their next turn`;
}
