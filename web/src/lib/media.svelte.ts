import { createSubscriber } from 'svelte/reactivity';

/** A media query as reactive state: `new Media('(min-width: 1100px)').current` re-reads when the
 * window crosses it. False before there is a window. Svelte's own `MediaQuery` wraps the query in
 * one pair of parentheses, which a compound query (`(hover: hover) and (pointer: fine)`) cannot
 * have, so this takes the whole query as written. */
export class Media {
	#list: MediaQueryList | undefined;
	#subscribe: () => void;

	constructor(query: string) {
		this.#list = typeof window === 'undefined' ? undefined : window.matchMedia(query);
		this.#subscribe = createSubscriber((update) => {
			this.#list?.addEventListener('change', update);
			return () => this.#list?.removeEventListener('change', update);
		});
	}

	get current(): boolean {
		this.#subscribe();
		return this.#list?.matches ?? false;
	}
}

/** The window the story workspace needs: the three panes only fit from here. */
export const WIDE = '(min-width: 1100px)';
/** A mouse: hover works and the pointer is exact. */
export const MOUSE = '(hover: hover) and (pointer: fine)';
