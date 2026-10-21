/** The keys the app keeps on the device, and their carry-over from the app's former name.
 *
 * Every key is `jinnverse-…`. Until 2026-10-21 the app was Lustjinn and the same entries were
 * `lustjinn-…` (#249); a reader who signed in or picked a theme under that name would otherwise
 * find the app signed out and navy again. So, once, each `lustjinn-…` entry is moved to its new
 * name: on the first load after the rename, before anything reads the storage, because this
 * module runs before every module that imports a key from it. A key already present under the
 * new name wins; the old entry goes either way.
 */

export const KEYS = {
	token: 'jinnverse-token',
	theme: 'jinnverse-theme',
	shelf: 'jinnverse-shelf',
	/** sessionStorage: the persona builder's pick, for this tab only. */
	builder: 'jinnverse-builder',
	turnHint: 'jinnverse-turn-hint'
} as const;

const FORMER = 'lustjinn-';
const CURRENT = 'jinnverse-';

/** Moves every `lustjinn-…` entry of `storage` to its `jinnverse-…` name; returns the new names. */
export function carryOver(storage: Storage): string[] {
	const moved: string[] = [];
	const former: string[] = [];
	for (let i = 0; i < storage.length; i++) {
		const key = storage.key(i);
		if (key?.startsWith(FORMER)) former.push(key);
	}
	for (const old of former) {
		const key = CURRENT + old.slice(FORMER.length);
		const value = storage.getItem(old);
		if (value !== null && storage.getItem(key) === null) storage.setItem(key, value);
		storage.removeItem(old);
		moved.push(key);
	}
	return moved;
}

// On the device, the move runs as this module loads — before the theme store, the token store
// or a page reads anything. A private window or a blocked storage throws; then there is nothing
// to carry over.
try {
	if (typeof localStorage !== 'undefined') carryOver(localStorage);
	if (typeof sessionStorage !== 'undefined') carryOver(sessionStorage);
} catch {
	/* nothing to move */
}
