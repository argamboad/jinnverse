import { describe, expect, it } from 'vitest';
import { enterHint, sends, type Keys } from './composer.ts';

function press(key: string, over: Partial<Keys> = {}): Keys {
	return { key, shiftKey: false, ctrlKey: false, metaKey: false, ...over };
}

describe('sends, on a desk', () => {
	it('sends on Enter', () => {
		expect(sends(press('Enter'), false)).toBe(true);
	});
	it('breaks the line on Shift+Enter', () => {
		expect(sends(press('Enter', { shiftKey: true }), false)).toBe(false);
	});
	it('sends on Ctrl+Enter and Cmd+Enter', () => {
		expect(sends(press('Enter', { ctrlKey: true }), false)).toBe(true);
		expect(sends(press('Enter', { metaKey: true }), false)).toBe(true);
	});
	it('never sends on another key', () => {
		expect(sends(press('a'), false)).toBe(false);
		expect(sends(press('a', { ctrlKey: true }), false)).toBe(false);
	});
});

describe('sends, on a touch keyboard', () => {
	it('breaks the line on Enter: only the Send button sends', () => {
		expect(sends(press('Enter'), true)).toBe(false);
	});
	it('breaks the line on Shift+Enter', () => {
		expect(sends(press('Enter', { shiftKey: true }), true)).toBe(false);
	});
	it('sends on Ctrl+Enter and Cmd+Enter, for a tablet with a keyboard', () => {
		expect(sends(press('Enter', { ctrlKey: true }), true)).toBe(true);
		expect(sends(press('Enter', { metaKey: true }), true)).toBe(true);
	});
});

describe('enterHint', () => {
	it('labels the Enter key Send on a desk', () => {
		expect(enterHint(false)).toBe('send');
	});
	it('keeps the Enter key on a touch keyboard', () => {
		expect(enterHint(true)).toBe('enter');
	});
});
