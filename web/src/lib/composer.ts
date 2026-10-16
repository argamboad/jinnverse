/** The modifier keys of a key press, as a `KeyboardEvent` carries them. */
export type Keys = Pick<KeyboardEvent, 'key' | 'shiftKey' | 'ctrlKey' | 'metaKey'>;

/** Whether a key press in the composer sends. On a touch keyboard Enter is a new line, as in every
 * other text box on the device, and only the Send button sends: a send is permanent and billed.
 * A desk keeps the chat convention, Enter sends and Shift+Enter breaks the line. Ctrl+Enter
 * (Cmd+Enter on Apple) sends on both, so a tablet with a keyboard has a key that sends. */
export function sends(keys: Keys, touch: boolean): boolean {
	if (keys.key !== 'Enter' || keys.shiftKey) return false;
	if (keys.ctrlKey || keys.metaKey) return true;
	return !touch;
}

/** The label the keyboard on screen puts on its Enter key: what Enter does there. */
export function enterHint(touch: boolean): 'enter' | 'send' {
	return touch ? 'enter' : 'send';
}
