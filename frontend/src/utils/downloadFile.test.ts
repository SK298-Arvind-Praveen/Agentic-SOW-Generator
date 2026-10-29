import { downloadWithNativeSaveAs, prepareDownload } from './downloadFile';

describe('native Save As download', () => {
  afterEach(() => {
    jest.restoreAllMocks();
    delete (window as any).showSaveFilePicker;
  });

  it('fetches the complete file before opening the picker and writes it', async () => {
    const events: string[] = [];
    const write = jest.fn(async () => { events.push('write'); });
    const close = jest.fn(async () => { events.push('close'); });
    (window as any).showSaveFilePicker = jest.fn(async (options: any) => {
      events.push(`picker:${options.suggestedName}`);
      return { createWritable: async () => ({ write, close }) };
    });
    const getBlob = jest.fn(async () => {
      events.push('fetch');
      return new Blob(['doc']);
    });

    await expect(downloadWithNativeSaveAs(getBlob, 'generated.docx')).resolves.toBe(true);
    expect(events).toEqual(['fetch', 'picker:generated.docx', 'write', 'close']);
    expect(write).toHaveBeenCalledWith(expect.any(Blob));
  });

  it('does not write when the native picker is cancelled after fetching', async () => {
    (window as any).showSaveFilePicker = jest.fn(async () => {
      throw new DOMException('cancelled', 'AbortError');
    });
    const getBlob = jest.fn(async () => new Blob(['doc']));

    await expect(downloadWithNativeSaveAs(getBlob, 'generated.docx')).resolves.toBe(false);
    expect(getBlob).toHaveBeenCalledTimes(1);
  });

  it('rejects an empty document before opening a writable stream', async () => {
    const createWritable = jest.fn();
    (window as any).showSaveFilePicker = jest.fn(async () => ({ createWritable }));
    await expect(downloadWithNativeSaveAs(async () => new Blob([]), 'SOW.docx')).rejects.toThrow('empty');
    expect(createWritable).not.toHaveBeenCalled();
    expect((window as any).showSaveFilePicker).not.toHaveBeenCalled();
  });

  it('does not create a local placeholder when fetching fails', async () => {
    (window as any).showSaveFilePicker = jest.fn();
    await expect(downloadWithNativeSaveAs(async () => { throw new Error('network'); }, 'failed.docx')).rejects.toThrow('network');
    expect((window as any).showSaveFilePicker).not.toHaveBeenCalled();
  });

  it('uses browser download when user activation expired while fetching', async () => {
    Object.defineProperty(window.URL, 'createObjectURL', { configurable: true, value: jest.fn(() => 'blob:valid') });
    const click = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    (window as any).showSaveFilePicker = jest.fn(async () => { throw new DOMException('activation expired', 'SecurityError'); });
    await expect(downloadWithNativeSaveAs(async () => new Blob(['valid']), 'ready.docx')).resolves.toBe(true);
    expect(click).toHaveBeenCalled();
  });

  it('falls back after a stale local write and aborts the failed stream', async () => {
    Object.defineProperty(window.URL, 'createObjectURL', { configurable: true, value: jest.fn(() => 'blob:valid') });
    const click = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const abort = jest.fn(async () => {});
    (window as any).showSaveFilePicker = jest.fn(async () => ({ createWritable: async () => ({
      write: async () => { throw new DOMException('State changed', 'InvalidStateError'); }, close: jest.fn(), abort,
    }) }));
    await expect(downloadWithNativeSaveAs(async () => new Blob(['valid']), 'Project - POC v31.docx')).resolves.toBe(true);
    expect(abort).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
  });

  it('does not suppress native security/scan failures as cancellation', async () => {
    (window as any).showSaveFilePicker = jest.fn(async () => ({ createWritable: async () => {
      throw new DOMException('Scan rejected', 'AbortError');
    } }));
    await expect(downloadWithNativeSaveAs(async () => new Blob(['valid']), 'SOW.docx')).rejects.toThrow('Scan rejected');
  });

  it('reserves the picker synchronously and safely normalizes the project name', async () => {
    const picker = jest.fn(async () => { throw new DOMException('cancelled', 'AbortError'); });
    (window as any).showSaveFilePicker = picker;
    const selection = prepareDownload('Tata | AI / Support - POC v31.docx');
    expect(picker).toHaveBeenCalledWith(expect.objectContaining({ suggestedName: 'Tata _ AI _ Support - POC v31.docx' }));
    await expect(selection).resolves.toBeNull();
  });

  it('falls back to the browser download mechanism when the picker is unavailable', async () => {
    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      value: jest.fn(() => 'blob:test'),
    });
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      value: jest.fn(),
    });
    const click = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    await expect(
      downloadWithNativeSaveAs(async () => new Blob(['doc']), 'generated.docx'),
    ).resolves.toBe(true);
    expect(click).toHaveBeenCalled();
    expect((click.mock.instances[0] as unknown as HTMLAnchorElement).download).toBe('generated.docx');
  });
});
