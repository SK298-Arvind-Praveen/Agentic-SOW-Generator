import { downloadWithNativeSaveAs } from './downloadFile';

describe('native Save As download', () => {
  afterEach(() => {
    jest.restoreAllMocks();
    delete (window as any).showSaveFilePicker;
  });

  it('opens the native picker before fetching and writes to the selected file', async () => {
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
    expect(events).toEqual(['picker:generated.docx', 'fetch', 'write', 'close']);
    expect(write).toHaveBeenCalledWith(expect.any(Blob));
  });

  it('does not fetch when the native picker is cancelled', async () => {
    (window as any).showSaveFilePicker = jest.fn(async () => {
      throw new DOMException('cancelled', 'AbortError');
    });
    const getBlob = jest.fn(async () => new Blob(['doc']));

    await expect(downloadWithNativeSaveAs(getBlob, 'generated.docx')).resolves.toBe(false);
    expect(getBlob).not.toHaveBeenCalled();
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
