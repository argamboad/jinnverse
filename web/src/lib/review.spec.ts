import { describe, expect, it } from 'vitest';
import type { Fact, Proposal } from './api.ts';
import { fine } from './money.ts';
import { condensePlan, confirmed, subjectOf, tally } from './review.ts';

function fact(id: string, subject: string, text: string): Fact {
	return {
		id,
		subject,
		text,
		valid_from_sequence: 1,
		valid_to_sequence: null,
		model: 'm',
		pinned: false,
		created_at: '2026-10-19T12:00:00Z'
	};
}

const rewrite: Proposal = {
	action: 'rewrite',
	facts: [fact('a', 'Rowan', 'is expected at the dock.')],
	subject: null,
	text: 'went to the dock.',
	reason: 'The dawn came.'
};
const retire: Proposal = {
	action: 'retire',
	facts: [fact('b', 'Rowan', 'carries a knife.')],
	subject: null,
	text: null,
	reason: 'Dropped.'
};
const merge: Proposal = {
	action: 'merge',
	facts: [fact('c', 'Rowan', 'took room seven.'), fact('d', 'Isaure', 'let the room.')],
	subject: 'Rowan and Isaure',
	text: 'Rowan took room seven from Isaure.',
	reason: 'One thing, twice.'
};

describe('the confirmed set', () => {
	it('carries only the kept proposals, by their facts', () => {
		expect(confirmed([rewrite, retire, merge], [true, false, true])).toEqual([
			{ action: 'rewrite', fact_ids: ['a'], text: 'went to the dock.' },
			{
				action: 'merge',
				fact_ids: ['c', 'd'],
				subject: 'Rowan and Isaure',
				text: 'Rowan took room seven from Isaure.'
			}
		]);
	});

	it('is empty when everything was dropped', () => {
		expect(confirmed([rewrite, retire], [false, false])).toEqual([]);
	});
});

describe('what the sheet shows', () => {
	it('names the subject from the proposal, else the first fact', () => {
		expect(subjectOf(merge)).toBe('Rowan and Isaure');
		expect(subjectOf(rewrite)).toBe('Rowan');
	});

	it('tallies the kept ones', () => {
		expect(tally([true, false, true])).toBe('2 of 3 on');
	});

	it('says what a condense would merge', () => {
		expect(
			condensePlan({ summaries: 6, from_sequence: 1, to_sequence: 278, tokens_before: 4300 })
		).toBe('6 summaries — turns 1–278, about 4,300 tokens of every reply — become one account.');
	});
});

describe('a fine cost', () => {
	it('shows a sliver to the tenth of a cent, and larger sums as money', () => {
		expect(fine('0.0031')).toBe('$0.0031');
		expect(fine('0.0003')).toBe('$0.0003');
		expect(fine('0.02')).toBe('$0.02');
		expect(fine(null)).toBe('—');
	});
});
