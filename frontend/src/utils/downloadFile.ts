const safeSuggestedName = (value: string): string => {
  const decoded = (() => {
    try { return decodeURIComponent(value); } catch { return value; }
  })();
  const cleaned = Array.from(decoded)
    .map((character) =>
      '<>:"/\\|?*'.includes(character) || character.charCodeAt(0) < 32
        ? '_'
        : character
    )
    .join('')
    .trim();
  return cleaned || 'document.docx';
};

type SaveFileHandle = {
  createWritable: () => Promise<{
    write: (data: Blob) => Promise<void>;
    close: () => Promise<void>;
    abort?: () => Promise<void>;
  }>;
};

type SavePickerWindow = Window & {
  showSaveFilePicker?: (options: {
    suggestedName: string;
    types?: Array<{ description: string; accept: Record<string, string[]> }>;
  }) => Promise<SaveFileHandle>;
};

const pickerType = (filename: string) => {
  const extension = /\.[A-Za-z0-9]{1,8}$/.exec(filename)?.[0].toLowerCase() || '.docx';
  const mime = extension === '.pdf'
    ? 'application/pdf'
    : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
  return [{ description: extension === '.pdf' ? 'PDF document' : 'Word document', accept: { [mime]: [extension] } }];
};

const activeDownloads = new Set<string>();

export const downloadWithNativeSaveAs = async (
  getBlob: () => Promise<Blob>,
  suggestedName: string,
): Promise<boolean> => {
  if (activeDownloads.has(suggestedName)) return false;
  activeDownloads.add(suggestedName);
  try {
    const blob = await getBlob();
    if (!blob.size) throw new Error('The document is empty. No file was written.');
    const save = await prepareDownload(suggestedName);
    if (!save) return false;
    await save(blob);
    return true;
  } finally {
    activeDownloads.delete(suggestedName);
  }
};

// Obtain the complete file first. Opening a picker while generating can leave
// an empty placeholder on disk. Browsers without activation use normal downloads.
export const prepareDownload = async (
  suggestedName: string,
): Promise<((blob: Blob, finalName?: string) => Promise<void>) | null> => {
  const safeSuggestion = safeSuggestedName(suggestedName);
  const picker = (window as SavePickerWindow).showSaveFilePicker;
  if (picker) {
    let handle: SaveFileHandle;
    try {
      // Open the native picker before starting the network request so the call
      // retains the browser's required user activation.
      handle = await picker.call(window, {
        suggestedName: safeSuggestion,
        types: pickerType(safeSuggestion),
      });
    } catch (error) {
      if (error && typeof error === 'object' && 'name' in error && error.name === 'AbortError') return null;
      if (error && typeof error === 'object' && 'name' in error && error.name === 'SecurityError') {
        return async (blob, finalName) => browserDownload(blob, safeSuggestedName(finalName || safeSuggestion));
      }
      throw error;
    }
    return async (blob, finalName) => {
      if (!blob.size) throw new Error('The document is empty. No file was written.');
      let writable: Awaited<ReturnType<SaveFileHandle['createWritable']>> | undefined;
      try {
        writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
      } catch (error) {
        try { await writable?.abort?.(); } catch { /* Preserve the original failure. */ }
        const name = error && typeof error === 'object' && 'name' in error ? error.name : '';
        if (name !== 'InvalidStateError' && name !== 'NotReadableError') throw error;
        console.warn('Native save failed; using standard browser download', error);
        browserDownload(blob, safeSuggestedName(finalName || safeSuggestion));
      }
    };
  }
  return async (blob, finalName) => browserDownload(blob, safeSuggestedName(finalName || safeSuggestion));
};

const browserDownload = (blob: Blob, filename: string): void => {
  if (!blob.size) throw new Error('The document is empty. No file was written.');
  // Firefox/Safari compatibility: use their standard download handling. The
  // browser's "ask where to save" preference controls whether a dialog opens.
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.setTimeout(() => window.URL.revokeObjectURL(url), 60000);
};
