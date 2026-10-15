/**
 * What rides beside a conversation: the dials in force, the meters, the last prompt's layers
 * and the running cost. One place, read by the phone's sheet and the desktop's rail alike, and
 * refreshed after each turn.
 */

import {
	api,
	type Audit,
	type Dial,
	type NewStatusField,
	type Status,
	type StatusFieldChanges,
	type StoryDial,
	type StorySpend,
	type Tracker
} from './api.ts';
import { parseContext, type Context } from './audit.ts';
import { toasts } from './toasts.svelte.ts';

export class Extras {
	pack = $state<Dial[]>([]);
	dials = $state<StoryDial[]>([]);
	trackers = $state<Tracker[]>([]);
	/** The status block's fields, what they hold and who is pinned; null until it is read. */
	status = $state<Status | null>(null);
	audit = $state<Audit | null>(null);
	spend = $state<StorySpend | null>(null);
	loaded = $state(false);

	constructor(readonly storyId: string) {}

	/** The newest reply's layers, as bars. */
	get context(): Context | null {
		return parseContext(this.audit?.turns[0]?.context);
	}

	async load() {
		try {
			[this.pack, this.dials, this.trackers] = await Promise.all([
				api.dialPack(),
				api.storyDials(this.storyId),
				api.trackers(this.storyId)
			]);
			await this.refresh();
			this.loaded = true;
		} catch (error) {
			toasts.show(
				'danger',
				'Could not read the story’s settings',
				error instanceof Error ? error.message : undefined
			);
		}
	}

	/** After a turn: the meters may have moved, the audit and the cost have a new line. */
	async refresh() {
		const [trackers, audit, spend, status] = await Promise.allSettled([
			api.trackers(this.storyId),
			api.audit(this.storyId),
			api.storySpend(this.storyId),
			api.status(this.storyId)
		]);
		if (trackers.status === 'fulfilled') this.trackers = trackers.value;
		if (status.status === 'fulfilled') this.status = status.value;
		if (audit.status === 'fulfilled') this.audit = audit.value;
		if (spend.status === 'fulfilled') this.spend = spend.value;
	}

	dial(key: string): Dial | undefined {
		return this.pack.find((d) => d.key === key);
	}

	/** Sets a dial at once and tells the API; if the API refuses, the dial goes back. */
	async setDial(key: string, value: string) {
		const dial = this.dial(key);
		const before = this.dials.find((d) => d.key === key);
		this.replaceDial(key, (d) => ({
			...d,
			stored: value,
			effective: value,
			label: labelOf(dial, value)
		}));
		try {
			const changed = await api.setDial(this.storyId, key, value);
			this.replaceDial(key, () => changed);
		} catch (error) {
			if (before) this.replaceDial(key, () => before);
			toasts.show('danger', 'Not set', error instanceof Error ? error.message : undefined);
		}
	}

	/** Puts a dial back on the card's own default at once; reverts if the API refuses. */
	async clearDial(key: string) {
		const dial = this.dial(key);
		const before = this.dials.find((d) => d.key === key);
		this.replaceDial(key, (d) => ({
			...d,
			stored: null,
			effective: dial?.default ?? null,
			label: labelOf(dial, dial?.default ?? null)
		}));
		try {
			await api.clearDial(this.storyId, key);
		} catch (error) {
			if (before) this.replaceDial(key, () => before);
			toasts.show('danger', 'Not cleared', error instanceof Error ? error.message : undefined);
		}
	}

	private replaceDial(key: string, change: (d: StoryDial) => StoryDial) {
		this.dials = this.dials.map((d) => (d.key === key ? change(d) : d));
	}

	async addTracker(body: Parameters<typeof api.addTracker>[1]) {
		try {
			const added = await api.addTracker(this.storyId, body);
			this.trackers = [...this.trackers, added];
			return true;
		} catch (error) {
			toasts.show('danger', 'Meter not added', error instanceof Error ? error.message : undefined);
			return false;
		}
	}

	async setTracker(name: string, value: number) {
		try {
			const changed = await api.changeTracker(this.storyId, name, { value });
			this.trackers = this.trackers.map((t) => (t.name === name ? changed : t));
		} catch (error) {
			toasts.show('danger', 'Meter not set', error instanceof Error ? error.message : undefined);
		}
	}

	/** Runs one change to the status block; the API answers with the whole state, which replaces
	 * ours. Returns whether it worked. */
	private async changeStatus(call: Promise<Status>, failed: string): Promise<boolean> {
		try {
			this.status = await call;
			return true;
		} catch (error) {
			toasts.show('danger', failed, error instanceof Error ? error.message : undefined);
			return false;
		}
	}

	adoptStarters(keys: string[]) {
		return this.changeStatus(api.adoptStatus(this.storyId, keys), 'Field not added');
	}

	addField(body: NewStatusField) {
		return this.changeStatus(api.addStatusField(this.storyId, body), 'Field not added');
	}

	changeField(key: string, body: StatusFieldChanges) {
		return this.changeStatus(api.changeStatusField(this.storyId, key, body), 'Field not changed');
	}

	removeField(key: string) {
		return this.changeStatus(api.removeStatusField(this.storyId, key), 'Field not deleted');
	}

	setPins(names: string[]) {
		return this.changeStatus(api.setStatusPins(this.storyId, names), 'Pins not saved');
	}

	/** Sets what a field holds, for the scene (`who` empty) or one character; blank clears it. */
	setStatusValue(field: string, who: string, value: string) {
		return this.changeStatus(
			api.setStatusValue(this.storyId, field, who || null, value),
			'Value not set'
		);
	}

	async removeTracker(name: string) {
		try {
			await api.removeTracker(this.storyId, name);
			this.trackers = this.trackers.filter((t) => t.name !== name);
		} catch (error) {
			toasts.show(
				'danger',
				'Meter not removed',
				error instanceof Error ? error.message : undefined
			);
		}
	}
}

/** A stored value as a screen shows it, mirroring the API's `dials.label`. */
export function labelOf(dial: Dial | undefined, value: string | null): string | null {
	if (!dial || value === null) return null;
	switch (dial.kind) {
		case 'scale': {
			const i = Number(value);
			return Number.isInteger(i) && dial.levels[i] ? dial.levels[i].label : value;
		}
		case 'toggle':
			return value === 'true' ? 'On' : 'Off';
		case 'choice':
			return dial.options.find((o) => o.key === value)?.label ?? value;
		case 'list':
			try {
				const items = JSON.parse(value) as unknown;
				return Array.isArray(items) ? items.join(', ') : value;
			} catch {
				return value;
			}
		case 'text':
			return value;
	}
}
