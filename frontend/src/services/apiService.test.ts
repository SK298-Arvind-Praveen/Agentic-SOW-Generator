import apiService from './apiService';

describe('authentication outage and session races', () => {
  afterEach(() => { jest.restoreAllMocks(); localStorage.clear(); });

  it('keeps the session during identity-store outages', async () => {
    localStorage.setItem('authToken', 'current');
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 503 }));
    await (apiService as any).authenticatedFetch('/api/preview/status/example');
    expect(localStorage.getItem('authToken')).toBe('current');
  });

  it('ignores late unauthorized responses from a previous session', async () => {
    localStorage.setItem('authToken', 'old');
    jest.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      localStorage.setItem('authToken', 'new');
      return new Response('{}', { status: 401 });
    });
    await (apiService as any).authenticatedFetch('/api/auth/me');
    expect(localStorage.getItem('authToken')).toBe('new');
  });

  it('still clears an actually invalid current session', async () => {
    localStorage.setItem('authToken', 'invalid');
    jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 401 }));
    await (apiService as any).authenticatedFetch('/api/auth/me');
    expect(localStorage.getItem('authToken')).toBeNull();
  });
});

describe('finalization readiness', () => {
  afterEach(() => jest.restoreAllMocks());
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

describe('account registration transport', () => {
  afterEach(() => jest.restoreAllMocks());

  it('submits signup details to the public signup endpoint', async () => {
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true, message: 'Check your email',
    }), { status: 201, headers: { 'Content-Type': 'application/json' } }));
    await apiService.signup({
      first_name: 'Asha', last_name: 'Rao', email: 'asha.rao@shellkode.com',
      employee_id: 101, business_unit: 'Cloud', password: 'secret1', confirm_password: 'secret1',
    });
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/auth/signup');
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({
      first_name: 'Asha', last_name: 'Rao', employee_id: 101, business_unit: 'Cloud',
    });
  });

  it('posts the signed token to account verification', async () => {
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    await apiService.verifyAccount('signed-token');
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/auth/verify');
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ token: 'signed-token' });
  });

  it('requests and completes password reset through public endpoints', async () => {
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify({
      success: true, message: 'Accepted',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    await apiService.forgotPassword('asha@shellkode.com');
    await apiService.resetPassword({
      token: 'reset-token', password: 'secret1', confirm_password: 'secret1',
    });
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/auth/forgot-password');
    expect(String(fetchMock.mock.calls[1][0])).toContain('/api/auth/reset-password');
  });

  it('requests a password-change link through the authenticated endpoint', async () => {
    localStorage.setItem('authToken', 'signed-session');
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true, message: 'Password reset link sent to your email.',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    await apiService.requestPasswordChange();

    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/auth/change-password-request');
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer signed-session');
  });

  it('refreshes the signed-in identity through the authenticated endpoint', async () => {
    localStorage.setItem('authToken', 'signed-session');
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true,
      user: { email: 'arvind.p@shellkode.com', role: 'USER', roles: ['USER'] },
      business_units: ['GenAI'],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    const response = await apiService.getCurrentUser();

    expect(response.user.role).toBe('USER');
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/auth/me');
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer signed-session');
  });
});

describe('semantic SOW search transport', () => {
  it.each(['poc', 'poc-to-production'] as const)('transmits Gantt selection for %s', async (mode) => {
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true, preview_id: 'timeline-preview',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    await apiService.generatePreview('Author', 'Client', mode, 'Delivery plan', 'Project',
      mode === 'poc-to-production' ? new File(['source'], 'poc.docx') : undefined,
      [], undefined, undefined, ['timelines_deliverables'], 'GenAI', undefined, undefined, 'gantt');
    const form = fetchMock.mock.calls[0][1]?.body as FormData;
    expect(form.get('timeline_format')).toBe('gantt');
  });
  afterEach(() => jest.restoreAllMocks());

  it('requests semantic results for the signed-in user', async () => {
    localStorage.setItem('authToken', 'signed-session');
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
    localStorage.setItem('authToken', 'signed-session');
    const fetchMock = jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      success: true, status: 'running', remaining: 12,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    const response = await apiService.prepareSemanticIndex();

    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/history/semantic-index');
    expect(response.status).toBe('running');
  });
});
