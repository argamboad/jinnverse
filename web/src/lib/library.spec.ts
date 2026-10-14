import { describe, expect, it } from 'vitest';
import {
	DESCRIPTION_LENGTH,
	blurb,
	hiddenCount,
	pieceBlurb,
	remaining,
	sentDescription
} from './library.ts';

describe('what a list shows under a name', () => {
	it('is the description when there is one', () => {
		expect(blurb({ description: 'The innkeeper.', preview: 'You are Elena…' })).toEqual({
			text: 'The innkeeper.',
			note: true
		});
	});

	it('is the start of the text when there is none, or it is blank', () => {
		expect(blurb({ description: null, preview: 'You are Elena…' })).toEqual({
			text: 'You are Elena…',
			note: false
		});
		expect(blurb({ description: '   ', preview: 'You are Elena…' }).note).toBe(false);
	});
});

describe('what a list shows under a piece', () => {
	it('is its description, or the start of its text', () => {
		expect(pieceBlurb({ description: 'The corgi', text: 'He has a corgi.' })).toEqual({
			text: 'The corgi',
			note: true
		});
		expect(pieceBlurb({ description: null, text: 'He has a corgi.' })).toEqual({
			text: 'He has a corgi.',
			note: false
		});
	});

	it('cuts a long text to what a description may hold', () => {
		expect(pieceBlurb({ description: null, text: 'x'.repeat(500) }).text).toHaveLength(200);
	});
});

describe('the hidden count', () => {
	it('says how many, and nothing when there are none', () => {
		expect(hiddenCount(2)).toBe(' (2)');
		expect(hiddenCount(0)).toBe('');
		expect(hiddenCount(undefined)).toBe('');
	});
});

describe('a description as typed and as sent', () => {
	it('counts down from the limit and goes negative past it', () => {
		expect(DESCRIPTION_LENGTH).toBe(200);
		expect(remaining('')).toBe(200);
		expect(remaining('x'.repeat(61))).toBe(139);
		expect(remaining('x'.repeat(201))).toBe(-1);
	});

	it('is sent trimmed, and blank clears it', () => {
		expect(sentDescription('  A cook.  ')).toBe('A cook.');
		expect(sentDescription('   ')).toBeNull();
		expect(sentDescription('')).toBeNull();
	});
});
