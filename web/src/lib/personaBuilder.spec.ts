import { describe, expect, it } from 'vitest';
import type { Slot } from './api.ts';
import {
	builderLine,
	count,
	groupSlots,
	hasText,
	isNeeded,
	keeping,
	missing,
	missingSentence,
	randomFor,
	rowHint,
	toggled
} from './personaBuilder.ts';

const SLOTS: Slot[] = [
	{ key: 'name', label: 'Name', paragraph: null },
	{ key: 'look', label: 'Identity and look', paragraph: 0 },
	{ key: 'home', label: 'Home', paragraph: 5 },
	{ key: 'vehicle', label: 'Vehicle', paragraph: 5 },
	{ key: 'pets', label: 'Pets', paragraph: 5 },
	{ key: 'humour', label: 'Humour', paragraph: 7 }
];

describe('the checklist', () => {
	it('gives each slot a row, and slots that share a paragraph one row together', () => {
		expect(groupSlots(SLOTS).map((g) => [g.key, g.label, g.slots.length])).toEqual([
			['name', 'Name', 1],
			['look', 'Identity and look', 1],
			['home+vehicle+pets', 'Home · Vehicle · Pets', 3],
			['humour', 'Humour', 1]
		]);
	});

	it('asks for a needed slot, lets an optional one go, and counts a shared row', () => {
		const [name, look, homeRow, humour] = groupSlots(SLOTS);
		expect(rowHint(name)).toBe('Pick one');
		expect(rowHint(look)).toBe('Pick one');
		expect(rowHint(humour)).toBe('Pick one, or leave it');
		expect(rowHint(homeRow)).toBe('One paragraph, up to 3 pieces');
	});

	it('counts the picked slots and says what is still needed', () => {
		expect(builderLine(SLOTS, {})).toBe('0 of 6 slots picked · 2 needed');
		expect(builderLine(SLOTS, { look: ['a'], pets: ['b', 'c'] })).toBe(
			'2 of 6 slots picked · 1 needed'
		);
		expect(builderLine(SLOTS, { name: ['n'], look: ['a'] })).toBe('2 of 6 slots picked');
	});
});

describe('what a persona is not made without', () => {
	it('needs a name and a look, and nothing else', () => {
		expect(isNeeded('name')).toBe(true);
		expect(isNeeded('look')).toBe(true);
		expect(isNeeded('home')).toBe(false);
		expect(isNeeded('pets')).toBe(false);
	});

	it('says what is missing, in the order a persona opens with it', () => {
		expect(missing({})).toEqual(['a name', 'an identity and look']);
		expect(missing({ look: ['a'] })).toEqual(['a name']);
		expect(missing({ name: ['a'], look: ['b'] })).toEqual([]);
	});

	it('asks for both in one sentence and for one in another', () => {
		expect(missingSentence({})).toBe(
			'A persona needs a name and an identity and look: pick them first.'
		);
		expect(missingSentence({ name: ['n'] })).toBe(
			'A persona needs an identity and look: pick it first.'
		);
		expect(missingSentence({ name: ['n'], look: ['l'] })).toBeNull();
	});

	it('counts an empty slot as not picked', () => {
		expect(missing({ name: [], look: [] })).toHaveLength(2);
	});
});

describe('changing a pick', () => {
	it('adds a piece and takes it back', () => {
		const one = toggled({}, 'home', 'a');
		expect(one).toEqual({ home: ['a'] });
		expect(toggled(one, 'home', 'a')).toEqual({});
	});

	it('keeps the order pieces were picked in, within a slot', () => {
		const picks = toggled(toggled({}, 'family', 'a'), 'family', 'b');
		expect(picks).toEqual({ family: ['a', 'b'] });
		expect(toggled(picks, 'family', 'a')).toEqual({ family: ['b'] });
	});

	it('never changes the pick it is given', () => {
		const before = { home: ['a'] };
		toggled(before, 'home', 'b');
		expect(before).toEqual({ home: ['a'] });
	});

	it('leaves the other slots alone', () => {
		expect(toggled({ look: ['l'] }, 'home', 'h')).toEqual({ look: ['l'], home: ['h'] });
	});

	it('puts back pieces that left the pool, and drops a slot left empty', () => {
		const picks = { look: ['gone'], home: ['a', 'gone'], pets: ['p'] };
		expect(keeping(picks, new Set(['a', 'p']))).toEqual({ home: ['a'], pets: ['p'] });
	});

	it('counts the pieces picked', () => {
		expect(count({})).toBe(0);
		expect(count({ home: ['a'], family: ['b', 'c'] })).toBe(3);
	});
});

describe('what there is to join', () => {
	it('is nothing for a name alone', () => {
		expect(hasText({})).toBe(false);
		expect(hasText({ name: ['n'] })).toBe(false);
		expect(hasText({ name: ['n'], look: ['l'] })).toBe(true);
		expect(hasText({ pets: ['p'] })).toBe(true);
		expect(hasText({ look: [] })).toBe(false);
	});
});

describe('picking at random', () => {
	it('picks by the roll, and never past the end', () => {
		expect(randomFor(['a', 'b', 'c'], 0)).toBe('a');
		expect(randomFor(['a', 'b', 'c'], 0.5)).toBe('b');
		expect(randomFor(['a', 'b', 'c'], 0.999)).toBe('c');
		expect(randomFor(['a', 'b', 'c'], 1)).toBe('c');
	});

	it('picks nothing from an empty slot', () => {
		expect(randomFor([], 0.3)).toBeNull();
	});
});
