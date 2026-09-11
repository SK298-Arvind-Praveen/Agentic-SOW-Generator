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
