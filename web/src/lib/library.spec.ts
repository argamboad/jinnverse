import { describe, expect, it } from 'vitest';
import {
	DESCRIPTION_LENGTH,
	blurb,
	entryMeta,
	hiddenCount,
	remaining,
	saveNote,
	sentDescription
} from './library.ts';

describe('the line under an entry', () => {
	it('gives the version and how many stories use it', () => {
		expect(entryMeta({ version: 2, used: 3 }, 'characters')).toBe('v2 · in 3 stories');
		expect(entryMeta({ version: 1, used: 1 }, 'personas')).toBe('v1 · in 1 story');
		expect(entryMeta({ version: 1, used: 0 }, 'personas')).toBe('v1 · unused');
	});
	it('gives only the version for a snippet, which no story keeps', () => {
		expect(entryMeta({ version: 4, used: 0 }, 'snippets')).toBe('v4');
	});
});

describe('the save bar', () => {
	it('says only that there are changes on a phone, or when nothing uses the entry', () => {
		expect(saveNote('character', 3, 4, false)).toBe('Unsaved changes');
		expect(saveNote('snippet', 0, 2, true)).toBe('Unsaved changes');
	});
	it('says which version the stories will read on a wide window', () => {
		expect(saveNote('character', 1, 4, true)).toBe(
			'Unsaved changes · the story using this character reads v4 from its next turn'
		);
		expect(saveNote('persona', 2, 2, true)).toBe(
			'Unsaved changes · the 2 stories using this persona read v2 from their next turn'
		);
	});
});

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
