/** Calls `fn` once the calls have stopped for `wait` ms, with the last call's arguments. `flush`
 * runs a pending call now (leaving a card, closing a panel); `cancel` drops it. */
export function debounce<A extends unknown[]>(fn: (...args: A) => void, wait: number) {
	let timer: ReturnType<typeof setTimeout> | undefined;
	let pending: A | undefined;

	function fire() {
		timer = undefined;
		const args = pending;
		pending = undefined;
		if (args) fn(...args);
	}

	const call = (...args: A) => {
		pending = args;
		clearTimeout(timer);
		timer = setTimeout(fire, wait);
	};
	call.flush = () => {
		clearTimeout(timer);
		fire();
	};
	call.cancel = () => {
		clearTimeout(timer);
		timer = undefined;
		pending = undefined;
	};
	return call;
}
