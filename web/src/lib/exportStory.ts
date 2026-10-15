import { api, type ExportFormat } from './api.ts';
import { saveBlob } from './download.ts';
import { toasts } from './toasts.svelte.ts';

const EXTENSIONS: Record<ExportFormat, string> = { markdown: 'md', json: 'json', text: 'txt' };

export const exportFormats: { id: ExportFormat; label: string }[] = [
	{ id: 'markdown', label: 'Markdown' },
	{ id: 'json', label: 'JSON' },
	{ id: 'text', label: 'Text' }
];

/** Fetches a story's transcript and saves it; a refusal becomes a toast. */
export async function exportStory(storyId: string, format: ExportFormat): Promise<void> {
	try {
		const { blob, name } = await api.exportStory(storyId, format);
		saveBlob(blob, name ?? `transcript.${EXTENSIONS[format]}`);
	} catch (error) {
		toasts.show('danger', 'Could not export', error instanceof Error ? error.message : undefined);
	}
}
