import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Dial, StoryDial } from './api.ts';

const calls = vi.hoisted(() => ({ setDial: vi.fn(), clearDial: vi.fn() }));
vi.mock('./api.ts', () => ({ api: calls }));

import { Extras } from './extras.svelte.ts';
import { toasts } from './toasts.svelte.ts';

const lust = {
	key: 'lust',
	kind: 'scale',
	default: '1',
	title: 'Lust',
	levels: [{ label: 'Cold' }, { label: 'Friendly' }, { label: 'Flirty' }]
} as unknown as Dial;

function setting(stored: string | null): StoryDial {
	return {
		key: 'lust',
		title: 'Lust',
		kind: 'scale',
		enabled: true,
		stored,
		effective: stored ?? '1',
		label: stored === null ? 'Friendly' : 'Flirty'
	};
}

function extrasWith(stored: string | null) {
	const extras = new Extras('story-1');
	extras.pack = [lust];
	extras.dials = [setting(stored)];
	return extras;
}

describe('Extras dials', () => {
	beforeEach(() => {
		calls.setDial.mockReset();
		calls.clearDial.mockReset();
		toasts.list = [];
	});

	it('shows a set dial before the API has answered', async () => {
		let answer: (d: StoryDial) => void = () => {};
		calls.setDial.mockReturnValue(new Promise<StoryDial>((resolve) => (answer = resolve)));
		const extras = extrasWith(null);

		const pending = extras.setDial('lust', '2');

		expect(extras.dials[0]).toMatchObject({ stored: '2', effective: '2', label: 'Flirty' });
		answer(setting('2'));
		await pending;
		expect(extras.dials[0].stored).toBe('2');
	});

	it('puts the dial back and says so when the API refuses', async () => {
		calls.setDial.mockRejectedValue(new Error('no'));
		const extras = extrasWith(null);

		await extras.setDial('lust', '2');

		expect(extras.dials[0]).toMatchObject({ stored: null, label: 'Friendly' });
		expect(toasts.list.some((t) => t.title === 'Not set')).toBe(true);
	});

	it('clears at once and restores the stored value when the API refuses', async () => {
		calls.clearDial.mockRejectedValue(new Error('no'));
		const extras = extrasWith('2');

		const pending = extras.clearDial('lust');
		expect(extras.dials[0]).toMatchObject({ stored: null, effective: '1', label: 'Friendly' });
		await pending;

		expect(extras.dials[0]).toMatchObject({ stored: '2', label: 'Flirty' });
	});
});
