import { describe, expect, it } from 'vitest';
import { apiHost, monthStart, tokenName } from './you.ts';

function jwt(claims: object): string {
	const part = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, '');
	return `${part({ alg: 'HS256' })}.${part(claims)}.signature`;
}

describe('tokenName', () => {
	it('reads the name a token was issued to', () => {
		expect(tokenName(jwt({ sub: 'reader', exp: 1 }))).toBe('reader');
	});
	it('says nothing for a missing, malformed or nameless token', () => {
		expect(tokenName(null)).toBeNull();
		expect(tokenName('not a token')).toBeNull();
		expect(tokenName(jwt({ exp: 1 }))).toBeNull();
	});
});

describe('monthStart', () => {
	it('is the first of the month at midnight UTC', () => {
		expect(monthStart(new Date('2026-10-15T19:24:00Z'))).toBe('2026-10-01T00:00:00.000Z');
		expect(monthStart(new Date('2026-12-31T23:59:59Z'))).toBe('2026-12-01T00:00:00.000Z');
	});
});

describe('apiHost', () => {
	it('names the host of an address, and keeps a bare path as it is', () => {
		expect(apiHost('https://lustjinn-staging.onrender.com')).toBe('lustjinn-staging.onrender.com');
		expect(apiHost('http://127.0.0.1:8000')).toBe('127.0.0.1:8000');
		expect(apiHost('/api-proxy')).toBe('/api-proxy');
	});
});
