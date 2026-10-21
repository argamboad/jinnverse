import { describe, expect, it } from 'vitest';
import { carryOver, KEYS } from './storage';

/** The slice of the Storage interface the carry-over uses, over a Map. */
function fakeStorage(entries: Record<string, string>): Storage {
	const map = new Map(Object.entries(entries));
	return {
		get length() {
			return map.size;
		},
		key: (index: number) => [...map.keys()][index] ?? null,
		getItem: (key: string) => map.get(key) ?? null,
		setItem: (key: string, value: string) => void map.set(key, value),
		removeItem: (key: string) => void map.delete(key),
		clear: () => map.clear()
	};
}

describe('the carry-over from the lustjinn- keys', () => {
	it('moves every former entry to its jinnverse- name and drops the old one', () => {
		const storage = fakeStorage({
			'lustjinn-token': 'eyJ…',
			'lustjinn-theme': 'light',
			unrelated: 'kept'
		});
		const moved = carryOver(storage);
		expect(moved.sort()).toEqual([KEYS.theme, KEYS.token]);
		expect(storage.getItem(KEYS.token)).toBe('eyJ…');
		expect(storage.getItem(KEYS.theme)).toBe('light');
		expect(storage.getItem('lustjinn-token')).toBeNull();
		expect(storage.getItem('lustjinn-theme')).toBeNull();
		expect(storage.getItem('unrelated')).toBe('kept');
	});

	it('keeps a value already stored under the new name', () => {
		const storage = fakeStorage({ 'lustjinn-theme': 'light', 'jinnverse-theme': 'dark' });
		carryOver(storage);
		expect(storage.getItem(KEYS.theme)).toBe('dark');
		expect(storage.getItem('lustjinn-theme')).toBeNull();
	});

	it('does nothing the second time', () => {
		const storage = fakeStorage({ 'jinnverse-shelf': 'personas' });
		expect(carryOver(storage)).toEqual([]);
		expect(storage.length).toBe(1);
	});

	it('names every key under the new prefix', () => {
		for (const key of Object.values(KEYS)) expect(key.startsWith('jinnverse-')).toBe(true);
	});
});
