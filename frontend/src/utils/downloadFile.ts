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

export const downloadWithNativeSaveAs = async (
  getBlob: () => Promise<Blob>,
  suggestedName: string,
): Promise<boolean> => {
  const safeSuggestion = safeSuggestedName(suggestedName);
  const picker = (window as SavePickerWindow).showSaveFilePicker;
  if (picker) {
    try {
      // Open the native picker before starting the network request so the call
      // retains the browser's required user activation.
      const handle = await picker.call(window, {
        suggestedName: safeSuggestion,
        types: pickerType(safeSuggestion),
      });
      const blob = await getBlob();
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return true;
    } catch (error) {
      if (error && typeof error === 'object' && 'name' in error && error.name === 'AbortError') return false;
      throw error;
    }
  }

  // Firefox/Safari compatibility: use their standard download handling. The
  // browser's "ask where to save" preference controls whether a dialog opens.
  const blob = await getBlob();
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = safeSuggestion;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
  return true;
};
