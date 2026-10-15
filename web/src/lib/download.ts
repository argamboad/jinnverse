/** Saving a fetched file: the name the server chose, and the browser's way of writing a blob. */

/** The file name in a `Content-Disposition` header, or null when there is none. */
export function fileNameOf(header: string | null): string | null {
	if (!header) return null;
	const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
	if (encoded) {
		try {
			return decodeURIComponent(encoded[1].trim());
		} catch {
			/* fall through to the plain form */
		}
	}
	const plain = /filename="?([^";]+)"?/i.exec(header);
	return plain ? plain[1].trim() : null;
}

/** Hands a blob to the browser as a download under `name`. */
export function saveBlob(blob: Blob, name: string) {
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = name;
	document.body.append(link);
	link.click();
	link.remove();
	// Revoking at once can cancel the download in some browsers; a tick later is safe.
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}
