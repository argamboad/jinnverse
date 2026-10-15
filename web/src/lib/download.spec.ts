import { describe, expect, it } from 'vitest';
import { fileNameOf } from './download';

describe('fileNameOf', () => {
	it('reads the quoted name the export sends', () => {
		expect(fileNameOf('attachment; filename="transcript-first-night-20261015-212100.md"')).toBe(
			'transcript-first-night-20261015-212100.md'
		);
	});

	it('reads a bare name and prefers the UTF-8 form when both are there', () => {
		expect(fileNameOf('attachment; filename=story.txt')).toBe('story.txt');
		expect(fileNameOf('attachment; filename="a.md"; filename*=UTF-8\'\'%C3%A9t%C3%A9.md')).toBe(
			'été.md'
		);
	});

	it('says nothing when there is no header', () => {
		expect(fileNameOf(null)).toBeNull();
		expect(fileNameOf('inline')).toBeNull();
	});
});
