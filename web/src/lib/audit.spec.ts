import { describe, expect, it } from 'vitest';
import { fade, layerLabel, parseContext, shares } from './audit';

describe('parseContext', () => {
	it('reads the layers, what was dropped, the total and the budget', () => {
		expect(
			parseContext(
				'character 2360 · world 417 · history 32 (1 dropped) · memories 530 · total 3339/6000'
			)
		).toEqual({
			layers: [
				{ name: 'character', tokens: 2360, dropped: 0 },
				{ name: 'world', tokens: 417, dropped: 0 },
				{ name: 'history', tokens: 32, dropped: 1 },
				{ name: 'memories', tokens: 530, dropped: 0 }
			],
			total: 3339,
			budget: 6000
		});
	});

	it('accepts a total without a budget, and nothing at all', () => {
		expect(parseContext('character 10 · total 10')).toEqual({
			layers: [{ name: 'character', tokens: 10, dropped: 0 }],
			total: 10,
			budget: null
		});
		expect(parseContext(null)).toBeNull();
		expect(parseContext('')).toBeNull();
		expect(parseContext('nonsense')).toBeNull();
	});
});

describe('the prompt bar', () => {
	it('shares the budget out by tokens, leaving the unused rest empty', () => {
		const ctx = parseContext('character 600 · history 300 · total 900/3000');
		expect(ctx).not.toBeNull();
		expect(shares(ctx!)).toEqual([20, 10]);
	});

	it('shares the total when there was no budget, so the bar fills', () => {
		const ctx = parseContext('character 300 · history 100 · total 400');
		expect(shares(ctx!)).toEqual([75, 25]);
	});

	it('fades from full to faint and names history as recent turns', () => {
		expect(fade(0, 4)).toBe(1);
		expect(fade(3, 4)).toBeCloseTo(0.35);
		expect(fade(0, 1)).toBe(1);
		expect(layerLabel('history')).toBe('recent turns');
		expect(layerLabel('world')).toBe('world');
	});
});
