import { beforeNavigate, goto } from '$app/navigation';

/** Asks before leaving an editor with unsaved changes: a link or Back gets a confirmation, and
 * closing or reloading the tab gets the browser's own "Leave site?". Call it while the component
 * is created. `leave` is the editor's own way out (after a save or a delete), which never asks. */
export function guardLeaving(dirty: () => boolean) {
	let leaving = false;
	beforeNavigate(({ cancel, willUnload }) => {
		if (leaving || !dirty()) return;
		// Cancelling an unload makes the browser ask; anything else is asked here.
		if (willUnload || !confirm('Leave without saving? Your changes will be lost.')) cancel();
	});
	return {
		async leave(to: string, options?: Parameters<typeof goto>[1]) {
			leaving = true;
			try {
				await goto(to, options);
			} finally {
				leaving = false;
			}
		}
	};
}
