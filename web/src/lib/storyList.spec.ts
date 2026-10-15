import { describe, expect, it } from 'vitest';
import type { Story } from './api.ts';
import { initial, when } from './storyList.ts';

const now = Date.parse('2026-10-15T12:00:00Z');

function story(over: Partial<Story> = {}): Story {
	return {
		id: 's1',
		name: 'First night at the Heron',
		character_id: 'c1',
		character_name: ' mara vell',
		persona_id: null,
		persona_name: null,
		created_at: '2026-10-01T09:00:00Z',
		last_message_at: null,
		last_message_preview: null,
		...over
	};
}

describe('initial', () => {
	it('is the first letter of the character, upper-cased, trimmed', () => {
		expect(initial(story())).toBe('M');
	});
	it('falls back to a question mark for a nameless character', () => {
		expect(initial(story({ character_name: '  ' }))).toBe('?');
	});
});

describe('when', () => {
	it('counts minutes, then hours, then says yesterday', () => {
		expect(when(story({ last_message_at: '2026-10-15T11:59:40Z' }), now)).toBe('now');
		expect(when(story({ last_message_at: '2026-10-15T11:25:00Z' }), now)).toBe('35m');
		expect(when(story({ last_message_at: '2026-10-15T09:00:00Z' }), now)).toBe('3h');
		expect(when(story({ last_message_at: '2026-10-14T09:00:00Z' }), now)).toBe('yesterday');
	});
	it('reads the creation time of a story nothing was said in', () => {
		expect(when(story({ created_at: '2026-10-15T11:50:00Z' }), now)).toBe('10m');
	});
	it('gives a date past a week', () => {
		expect(when(story({ last_message_at: '2026-09-01T09:00:00Z' }), now)).not.toMatch(
			/ago|\dh|\dm/
		);
	});
});
