import type { Story } from './api.ts';

/** The letter on a story's tile: the first of its character's name. */
export function initial(story: Story): string {
	return story.character_name.trim().charAt(0).toUpperCase() || '?';
}

/** How long ago a story last moved, as the list shows it: "now", "5m", "3h", "yesterday", the
 * weekday within a week, then the date. */
export function when(story: Story, now = Date.now()): string {
	const at = new Date(story.last_message_at ?? story.created_at);
	const minutes = Math.round((now - at.getTime()) / 60000);
	if (minutes < 1) return 'now';
	if (minutes < 60) return `${minutes}m`;
	const hours = Math.round(minutes / 60);
	if (hours < 24) return `${hours}h`;
	const days = Math.round(hours / 24);
	if (days === 1) return 'yesterday';
	if (days < 7) return at.toLocaleDateString(undefined, { weekday: 'short' });
	return at.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}
