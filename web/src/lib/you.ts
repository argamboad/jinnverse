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
