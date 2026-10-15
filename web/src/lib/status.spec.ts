import { describe, expect, it } from 'vitest';
import type { StatusField, StatusValue } from './api.ts';
import { grouped, inScene, parseWords, RECENT_TURNS, sceneLines, scopeNote } from './status.ts';

function field(key: string, scope: 'scene' | 'character', position: number, enabled = true) {
	return {
		key,
		label: key[0].toUpperCase() + key.slice(1),
		icon: null,
		hint: null,
		kind: 'text',
		scope,
		words: null,
		enabled,
		position
	} satisfies StatusField;
}

function value(f: string, who: string, text: string, seen: number | null = 1): StatusValue {
	return { field: f, who, value: text, by_hand: false, seen };
}

const fields = [
	field('time', 'scene', 0),
	field('place', 'scene', 1, false),
	field('outfit', 'character', 2),
	field('mood', 'character', 3)
];

describe('scopeNote', () => {
	it('says what a field belongs to', () => {
		expect(scopeNote({ scope: 'scene', kind: 'text' })).toBe('Scene');
		expect(scopeNote({ scope: 'character', kind: 'text' })).toBe('Each character');
		expect(scopeNote({ scope: 'character', kind: 'words' })).toBe('Each character · words');
	});
});

describe('parseWords', () => {
	it('splits on commas, bars and lines, and drops blanks and repeats', () => {
		expect(parseWords('Guarded, teasing | Rattled;\n guarded ,, ')).toEqual([
			'Guarded',
			'teasing',
			'Rattled'
		]);
		expect(parseWords('  ')).toEqual([]);
	});
});

describe('grouped', () => {
	it('puts the scene first, then characters by name, each in field order', () => {
		const values = [
			value('mood', 'Sammy', 'Calm'),
			value('outfit', 'Peach', 'a robe'),
			value('mood', 'Peach', 'Guarded'),
			value('time', '', 'Day 1'),
			value('gone', 'Peach', 'x')
		];

		const out = grouped({ fields, values });

		expect(out.map((s) => s.who)).toEqual(['', 'Peach', 'Sammy']);
		expect(out[1].lines.map((l) => l.field.key)).toEqual(['outfit', 'mood']);
	});
});

describe('sceneLines', () => {
	it('keeps only the scene values of fields that are on', () => {
		const values = [value('time', '', 'Day 1'), value('place', '', 'the bar')];

		expect(sceneLines({ fields, values }).map((l) => l.value)).toEqual(['Day 1']);
	});
});

describe('inScene', () => {
	const values = [
		value('outfit', 'Peach', 'a robe', 30),
		value('mood', 'Peach', 'Calm', 28),
		value('outfit', 'Sammy', 'a hoodie', 30 - RECENT_TURNS),
		value('outfit', 'Old Friend', 'a suit', 30 - RECENT_TURNS - 1),
		value('time', '', 'Day 1', 30)
	];

	it('lists who wrote a line recently, most recent first, and not the scene', () => {
		expect(inScene({ fields, values, pins: [] }, 30)).toEqual([
			{ who: 'Peach', pinned: false },
			{ who: 'Sammy', pinned: false }
		]);
	});

	it('puts pinned characters first and keeps them however long they have been away', () => {
		expect(inScene({ fields, values, pins: ['old friend'] }, 30)).toEqual([
			{ who: 'Old Friend', pinned: true },
			{ who: 'Peach', pinned: false },
			{ who: 'Sammy', pinned: false }
		]);
	});

	it('shows no one pinned who has no line yet', () => {
		expect(inScene({ fields, values: [], pins: ['Peach'] }, 3)).toEqual([]);
	});
});
