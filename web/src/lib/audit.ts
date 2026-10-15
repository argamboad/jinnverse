/** Reads the audit line kept with each reply — `character 2360 · world 417 · history 32 (1
 * dropped) · total 5278/6000` — into layers a screen can draw as bars. */

export interface Layer {
	name: string;
	tokens: number;
	dropped: number;
}

export interface Context {
	layers: Layer[];
	total: number;
	budget: number | null;
}

/** The prompt's layers are named in the code; a few read better as plain words on a screen. */
const LABELS: Record<string, string> = { history: 'recent turns' };

export function layerLabel(name: string): string {
	return LABELS[name] ?? name;
}

/** Each layer's share of the stacked bar, in percent: of the budget when the prompt had one (the
 * empty remainder is room left), of the total when it had none (the bar fills). */
export function shares(context: Context): number[] {
	const whole = context.budget ?? Math.max(context.total, 1);
	return context.layers.map((layer) => Math.min(100, (layer.tokens / whole) * 100));
}

/** The opacity of the i-th of n segments: the first full, the last faint, so neighbours differ. */
export function fade(i: number, n: number): number {
	return n <= 1 ? 1 : 1 - (0.65 * i) / (n - 1);
}

const LAYER = /^(\w+) (\d+)(?: \((\d+) dropped\))?$/;
const TOTAL = /^total (\d+)(?:\/(\d+))?$/;

export function parseContext(line: string | null | undefined): Context | null {
	if (!line) return null;
	const layers: Layer[] = [];
	let total = 0;
	let budget: number | null = null;
	for (const part of line.split(' · ')) {
		const t = TOTAL.exec(part.trim());
		if (t) {
			total = Number(t[1]);
			budget = t[2] ? Number(t[2]) : null;
			continue;
		}
		const l = LAYER.exec(part.trim());
		if (l) layers.push({ name: l[1], tokens: Number(l[2]), dropped: l[3] ? Number(l[3]) : 0 });
	}
	if (layers.length === 0 && total === 0) return null;
	return { layers, total, budget };
}
