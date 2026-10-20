/** The small rules behind the You screen: who is signed in, where "this month" starts, which API. */

/** The name a token was issued to (its `sub`), for display; null when it cannot be read. The
 * token is read, not checked: the API checks it on every call. */
export function tokenName(token: string | null): string | null {
	if (!token) return null;
	try {
		const payload = token.split('.')[1];
		const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
		const claims = JSON.parse(json) as { sub?: unknown };
		return typeof claims.sub === 'string' && claims.sub ? claims.sub : null;
	} catch {
		return null;
	}
}

/** The first moment of the current month in UTC, as the spend report's `from_at`. */
export function monthStart(now = new Date()): string {
	return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)).toISOString();
}

/** The API as the footer names it: its host, or the address as given when it is only a path
 * (the dev server's proxy). */
export function apiHost(url: string): string {
	try {
		return new URL(url).host;
	} catch {
		return url;
	}
}

const count = (n: number, one: string, many: string) =>
	`${n.toLocaleString('en-US')} ${n === 1 ? one : many}`;

/** What the Deleted stories card says about the deleted stories still kept. */
export function keptLine(kept: { stories: number; messages: number }): string {
	if (kept.stories === 0) return 'Nothing to erase.';
	const verb = kept.stories === 1 ? 'keeps' : 'keep';
	return `${count(kept.stories, 'deleted story', 'deleted stories')} still ${verb} ${count(kept.messages, 'message', 'messages')} and their memory.`;
}

/** The question asked before erasing, and the toast after. */
export function eraseQuestion(stories: number): string {
	return `Erase ${count(stories, 'story', 'stories')} for good?`;
}
export function erasedLine(stories: number): string {
	return `Erased ${count(stories, 'story', 'stories')}`;
}
