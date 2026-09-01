import apiService from './apiService';

describe('supporting-document preview transport', () => {
  afterEach(() => {
    jest.restoreAllMocks();
    localStorage.clear();
  });

  it('sends every supporting document and accepts a matching extraction receipt', async () => {
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true,
      preview_id: 'preview-1',
      supporting_documents_received: 1,
      supporting_documents_extracted: 1,
      supporting_context_chars: 240,
    }), { status: 202, headers: { 'Content-Type': 'application/json' } }));
    const source = new File(['BRD-17 maker-checker queue'], 'requirements.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });

    const result = await apiService.generatePreview(
      'Arvind', 'Axis Securities', 'poc', '', 'Settlement Operations',
      undefined, [source], undefined, undefined, ['project_overview'], 'Cloud',
    );

    expect(result.success).toBe(true);
    const request = fetchMock.mock.calls[0][1];
    const body = request?.body as FormData;
    expect(body.getAll('supporting_docs')).toHaveLength(1);
    expect(body.get('supporting_doc_count')).toBe('1');
    expect(body.get('additional_details')).toBe('');
    expect(body.has('objective')).toBe(false);
  });

  it('stops when the server does not confirm document ingestion', async () => {
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true,
      preview_id: 'unsafe-preview',
      supporting_documents_received: 0,
      supporting_documents_extracted: 0,
    }), { status: 202, headers: { 'Content-Type': 'application/json' } }));
    const source = new File(['requirements'], 'requirements.docx');

    const result = await apiService.generatePreview(
      'Arvind', 'Axis Securities', 'poc', '', 'Settlement Operations',
      undefined, [source], undefined, undefined, ['project_overview'], 'Cloud',
    );

    expect(result.success).toBe(false);
    expect(result.error).toBe('One or more supporting documents could not be read. Generation was stopped.');
  });

  it('shows the backend unsupported-file message without ingestion counters', async () => {
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: false,
      error: 'Unsupported file type. Supported files: PDF, Word, Excel, and TXT.',
      supporting_documents_received: 1,
      supporting_documents_extracted: 0,
    }), { status: 415, headers: { 'Content-Type': 'application/json' } }));
    const source = new File(['binary'], 'requirements.zip');

    const result = await apiService.generatePreview(
      'Arvind', 'Axis Securities', 'poc', '', 'Settlement Operations',
      undefined, [source], undefined, undefined, ['project_overview'], 'Cloud',
    );

    expect(result.error).toBe('Unsupported file type. Supported files: PDF, Word, Excel, and TXT.');
    expect(result.error).not.toContain('received');
  });
});
