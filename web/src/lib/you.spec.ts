import { describe, expect, it } from 'vitest';
import { apiHost, erasedLine, eraseQuestion, keptLine, monthStart, tokenName } from './you.ts';

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

describe('keptLine', () => {
	it('says there is nothing to erase when nothing is deleted', () => {
		expect(keptLine({ stories: 0, messages: 0 })).toBe('Nothing to erase.');
	});
	it('counts the stories and their messages, singular and plural, with separators', () => {
		expect(keptLine({ stories: 1, messages: 1 })).toBe(
			'1 deleted story still keeps 1 message and their memory.'
		);
		expect(keptLine({ stories: 12, messages: 1646 })).toBe(
			'12 deleted stories still keep 1,646 messages and their memory.'
		);
	});
});

describe('eraseQuestion and erasedLine', () => {
	it('name how many stories, singular and plural', () => {
		expect(eraseQuestion(1)).toBe('Erase 1 story for good?');
		expect(eraseQuestion(3)).toBe('Erase 3 stories for good?');
		expect(erasedLine(1)).toBe('Erased 1 story');
		expect(erasedLine(12)).toBe('Erased 12 stories');
	});
});
