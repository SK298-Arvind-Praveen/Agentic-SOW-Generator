import apiService from './apiService';

it('trims preview names even when submitted without a blur event', async () => {
  const request = jest.spyOn(apiService as any, 'authenticatedFetch')
    .mockResolvedValue(new Response(JSON.stringify({ success: true, preview_id: 'trim-test' })));
  try {
    await apiService.generatePreview('  Arvind P  ', '  Example  Company  ', 'poc', 'scope', '  Project Name  ');
    const body = request.mock.calls[0][1] as RequestInit;
    const form = body.body as FormData;
    expect(form.get('author_name')).toBe('Arvind P');
    expect(form.get('company_name')).toBe('Example  Company');
    expect(form.get('project_name')).toBe('Project Name');
  } finally { request.mockRestore(); }
});

describe('authentication outage and session races', () => {
  afterEach(() => { jest.restoreAllMocks(); localStorage.clear(); apiService.clearSession(); });

  it('keeps the session during identity-store outages', async () => {
    apiService.setSessionCsrf('current');
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 503 }));
    await (apiService as any).authenticatedFetch('/api/preview/status/example');
    expect((apiService as any).csrfToken).toBe('current');
  });

  it('ignores late unauthorized responses from a previous session', async () => {
    apiService.setSessionCsrf('old');
    jest.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      apiService.setSessionCsrf('new');
      return new Response('{}', { status: 401 });
    });
    await (apiService as any).authenticatedFetch('/api/auth/me');
    expect((apiService as any).csrfToken).toBe('new');
  });

  it('still clears an actually invalid current session', async () => {
    apiService.setSessionCsrf('invalid');
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 401 }));
    await (apiService as any).authenticatedFetch('/api/auth/me');
    expect((apiService as any).csrfToken).toBe('');
  });

  it('retries a transient pre-route auth failure and finalizes the same preview once', async () => {
    apiService.setSessionCsrf('current');
    const delay = jest.spyOn(apiService as any, 'delay').mockResolvedValue(undefined);
    const fetchMock = jest.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({code:'AUTH_SERVICE_UNAVAILABLE',retryable:true}),
        {status:503,headers:{'Retry-After':'5'}}))
      .mockResolvedValueOnce(new Response(JSON.stringify({success:true,document_id:'d1',s3_url:'https://files/d1.docx'})));
    expect(await apiService.finalizeSOW('p1')).toMatchObject({success:true,document_id:'d1'});
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(delay).toHaveBeenCalledWith(5000);
    expect(fetchMock.mock.calls[0][1]?.body).toEqual(fetchMock.mock.calls[1][1]?.body);
    expect((apiService as any).csrfToken).toBe('current');
  });

  it('stops after one auth retry and retains the session and explanation', async () => {
    apiService.setSessionCsrf('current');
    jest.spyOn(apiService as any, 'delay').mockResolvedValue(undefined);
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      new Response(JSON.stringify({code:'AUTH_SERVICE_UNAVAILABLE',error:'Sign-in temporarily unavailable',retryable:true}),{status:503}));
    expect(await apiService.finalizeSOW('p1')).toMatchObject({success:false,code:'AUTH_SERVICE_UNAVAILABLE'});
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect((apiService as any).csrfToken).toBe('current');
  });

  it('does not retry a credential or permissions outage', async () => {
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({code:'AUTH_SERVICE_UNAVAILABLE',retryable:false}),{status:503}));
    expect((await apiService.finalizeSOW('p1')).success).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does not replay a request if the session changes during the retry delay', async () => {
    apiService.setSessionCsrf('old');
    jest.spyOn(apiService as any,'delay').mockImplementation(async () => apiService.setSessionCsrf('new'));
    const fetchMock=jest.spyOn(globalThis,'fetch').mockResolvedValue(new Response(
      JSON.stringify({code:'AUTH_SERVICE_UNAVAILABLE',retryable:true}),{status:503}));
    await (apiService as any).authenticatedFetch('/api/finalize');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect((apiService as any).csrfToken).toBe('new');
  });

  it('retries the download auth check and returns the actual document bytes', async () => {
    jest.spyOn(apiService as any,'delay').mockResolvedValue(undefined);
    const fetchMock=jest.spyOn(globalThis,'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({code:'AUTH_SERVICE_UNAVAILABLE',retryable:true}),{status:503}))
      .mockResolvedValueOnce(new Response('docx bytes'));
    expect((await apiService.downloadDocument('https://files/d1.docx','d1')).size).toBe(10);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe('finalization readiness', () => {
  afterEach(() => jest.restoreAllMocks());
  it.each(['AWS_PRICING_STALE', 'ARCHITECTURE_REGENERATION_REQUIRED'])(
    'preserves the server explanation and code for %s without retrying', async code => {
      const error = 'Resolve this preview validation issue before finalizing.';
      const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(JSON.stringify({ success: false, code, error }), { status: 409, statusText: 'CONFLICT' })
      );
      expect(await apiService.finalizeSOW('p1')).toMatchObject({ success: false, code, error });
      expect(fetchMock).toHaveBeenCalledTimes(1);
    }
  );
  it('waits for a background save over HTTP and then finalizes the same preview', async () => {
    jest.spyOn(apiService as any, 'delay').mockResolvedValue(undefined);
    const fetchMock = jest.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ success: true, processing: true, status: 'processing' }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ success: true, document_id: 'd1', s3_url: 'https://files/final.docx' }), { status: 200 }));
    expect(await apiService.finalizeSOW('p1')).toMatchObject({ success: true, document_id: 'd1' });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    for (const [, options] of fetchMock.mock.calls) {
      expect(JSON.parse(String(options?.body))).toEqual({ preview_id: 'p1' });
    }
  });
  it('falls back to the HTTP error for non-JSON failures', async () => {
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('unavailable', { status: 503, statusText: 'Unavailable' }));
    expect(await apiService.finalizeSOW('p1')).toMatchObject({ success: false, error: 'HTTP 503: Unavailable' });
  });
  it('waits through processing responses instead of reporting a save', async () => {
    const request = jest.spyOn(apiService as any, 'makeRequestJSON')
      .mockResolvedValueOnce({ success: true, processing: true })
      .mockResolvedValueOnce({ success: true, document_id: 'd31', s3_url: 'https://files/final.docx', result: { version: 'v31' } });
    jest.spyOn(apiService as any, 'delay').mockResolvedValue(undefined);
    const result = await apiService.finalizeSOW('preview31');
    expect(request).toHaveBeenCalledTimes(2);
    expect(result.result.version).toBe('v31');
  });
  it('rejects success without a durable document', async () => {
    jest.spyOn(apiService as any, 'makeRequestJSON').mockResolvedValue({ success: true });
    expect((await apiService.finalizeSOW('preview31')).success).toBe(false);
  });
});

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

  it('sends the selected custom template with mixed section ordering', async () => {
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true, preview_id: 'preview-custom',
    }), { status: 202, headers: { 'Content-Type': 'application/json' } }));
    await apiService.generatePreview(
      'Arvind', 'Example', 'poc', 'Build a workflow', 'Project', undefined, [],
      undefined, undefined, ['project_overview', 'custom_ab12_governance'], 'Cloud',
      undefined, 'ab12template',
    );
    const body = fetchMock.mock.calls[0][1]?.body as FormData;
    expect(body.get('custom_template_id')).toBe('ab12template');
    expect(JSON.parse(String(body.get('selected_sow_sections')))).toEqual([
      'project_overview', 'custom_ab12_governance',
    ]);
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

describe('preview draft transport', () => {
  afterEach(() => jest.restoreAllMocks());

  it('waits for an in-progress draft save instead of treating 202 as failure', async () => {
    jest.spyOn(apiService as any, 'delay').mockResolvedValue(undefined);
    const fetchMock = jest.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ success: false, processing: true }), { status: 202 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ success: true, status: 'draft', document_id: 'd1' }), { status: 200 }));
    const result = await apiService.savePreviewAsDraft('p1');
    expect(result.document_id).toBe('d1');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('supports heartbeat, durable save, discard, open, and draft deletion', async () => {
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockImplementation(async input => {
      const url = String(input);
      const payload = url.endsWith('/draft/open')
        ? { success: true, preview_id: 'restored-preview' }
        : { success: true };
      return new Response(JSON.stringify(payload), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    await apiService.heartbeatPreview('preview 1');
    await apiService.savePreviewAsDraft('preview 1');
    await apiService.discardPreview('preview 1');
    const opened = await apiService.openDraftSOW('document 1');
    await apiService.deleteDraftSOW('document 1');

    expect(opened.preview_id).toBe('restored-preview');
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/preview/preview%201/heartbeat');
    expect(String(fetchMock.mock.calls[1][0])).toContain('/api/preview/preview%201/draft');
    expect(fetchMock.mock.calls[2][1]?.method).toBe('DELETE');
    expect(String(fetchMock.mock.calls[3][0])).toContain('/api/sows/document%201/draft/open');
    expect(fetchMock.mock.calls[4][1]?.method).toBe('DELETE');
  });
});

describe('Google cookie session transport', () => {
  afterEach(() => { jest.restoreAllMocks(); apiService.clearSession(); });
  it('gets CSRF from the cookie session and sends it only on mutations', async () => {
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true, user: {email:'user@shellkode.com'}, csrf_token:'csrf', business_units:[],
    })));
    await apiService.getCurrentUser();
    await (apiService as any).authenticatedFetch('/api/example', {method:'POST', body:'data'});
    expect(fetchMock.mock.calls[0][1]?.credentials).toBe('include');
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBeNull();
    expect(new Headers(fetchMock.mock.calls[1][1]?.headers).get('X-CSRF-Token')).toBe('csrf');
  });
  it('logs out on the server before discarding the local session', async () => {
    apiService.setSessionCsrf('csrf');
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{"success":true}'));
    await apiService.logout();
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/auth/logout');
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('X-CSRF-Token')).toBe('csrf');
    expect((apiService as any).csrfToken).toBe('');
  });
});

describe('semantic SOW search transport', () => {
  it.each(['poc', 'production'] as const)('transmits Gantt selection for %s', async (mode) => {
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true, preview_id: 'timeline-preview',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    await apiService.generatePreview('Author', 'Client', mode, 'Delivery plan', 'Project',
      undefined,
      [], undefined, undefined, ['timelines_deliverables'], 'GenAI', undefined, undefined, 'gantt');
    const form = fetchMock.mock.calls[0][1]?.body as FormData;
    expect(form.get('timeline_format')).toBe('gantt');
  });
  afterEach(() => jest.restoreAllMocks());

  it('requests semantic results for the signed-in user', async () => {
    apiService.setSessionCsrf('signed-session');
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true,
      threshold: 50,
      documents: [{ document_id: 'latest', similarity_score: 87.25 }],
      count: 1,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    const response = await apiService.semanticSearchDocuments('customer support automation', {
      mine: true, limit: 1000,
    });

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('/api/history/semantic-search?');
    expect(url).toContain('q=customer+support+automation');
    expect(url).toContain('mine=true');
    expect(response.documents[0].similarity_score).toBe(87.25);
  });

  it('starts the persistent semantic index warm-up', async () => {
    apiService.setSessionCsrf('signed-session');
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true, status: 'running', remaining: 12,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    const response = await apiService.prepareSemanticIndex();

    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/history/semantic-index');
    expect(response.status).toBe('running');
  });
});
