import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { debounce } from './debounce.ts';

describe('debounce', () => {
	beforeEach(() => vi.useFakeTimers());
	afterEach(() => vi.useRealTimers());

	it('calls once, with the last arguments, after the calls stop', () => {
		const fn = vi.fn();
		const call = debounce(fn, 300);

		call(1);
		vi.advanceTimersByTime(200);
		call(2);
		vi.advanceTimersByTime(200);
		expect(fn).not.toHaveBeenCalled();
		vi.advanceTimersByTime(100);

		expect(fn).toHaveBeenCalledTimes(1);
		expect(fn).toHaveBeenCalledWith(2);
	});

	it('flush runs a pending call now, and only once', () => {
		const fn = vi.fn();
		const call = debounce(fn, 300);

		call('a');
		call.flush();
		call.flush();
		vi.advanceTimersByTime(1000);

		expect(fn).toHaveBeenCalledTimes(1);
		expect(fn).toHaveBeenCalledWith('a');
	});

	it('cancel drops a pending call', () => {
		const fn = vi.fn();
		const call = debounce(fn, 300);

		call('a');
		call.cancel();
		vi.advanceTimersByTime(1000);

		expect(fn).not.toHaveBeenCalled();
	});
});
