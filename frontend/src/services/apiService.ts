/**
 * API Service
 * Handles all API requests for SOW generation
 */

import API_CONFIG from '../config/apiConfig';

export type SOWMode = 'POC' | 'PROD' | 'POC_TO_PROD';

export interface GenerateSOWRequest {
  author_name: string;
  company_name: string;
  mode: SOWMode;
  objective: string;
  project_name: string;
}

export interface GenerateSOWResponse {
  success: boolean;
  preview_id?: string;
  data?: {
    documentId: string;
    documentUrl: string;
    fileName: string;
    generatedAt: string;
  };
  error?: string;
  message?: string;
  [key: string]: any;
}

export interface Document {
  author?: string;
  author_name?: string;
  company?: string;
  company_name?: string;
  customer_name?: string;
  date?: string;
  created_at?: string;
  timestamp?: string;
  document_id?: string;
  doc_id?: string;
  id?: string;
  mode?: string;
  sow_type?: string;
  type?: string;
  name?: string;
  project_name?: string;
  title?: string;
  s3_url?: string;
  download_url?: string;
  url?: string;
  drive_link?: string;
  status?: string;
  progress?: number;
  current_step?: string;
  is_processing?: boolean;
  task_id?: string;
  version?: string;
  document_date?: string;
  docCount?: number;
  business_unit?: string;
  owner_email?: string;
  owner_name?: string;
  total_tokens?: number | string;
  similarity_score?: number;
  project_id?: string;
  account_id?: string;
  parent_document_id?: string;
  source_scope_id?: string;
  draft_preview_s3_url?: string;
  source_documents?: SourceDocument[];
  token_usage?: {
    total_input_tokens?: number;
    total_output_tokens?: number;
    total_tokens?: number;
    api_calls?: number;
    models?: Record<string, number>;
  };
}

export interface SourceDocument {
  source_id: string;
  filename: string;
  content_hash: string;
  revision: number;
  uploaded_at: string;
  comparison?: 'unchanged' | 'changed' | 'new_or_replaced';
  previous_source_id?: string;
  extracted_characters?: number;
  reused?: boolean;
}

export interface CustomTemplateSection {
  id: string;
  label: string;
  order: number;
}

export interface CustomSowTemplate {
  template_id: string;
  name: string;
  author: string;
  owner_email: string;
  source_filename?: string;
  sections: CustomTemplateSection[];
  saved: boolean;
  can_delete: boolean;
  output_path?: string;
}

export interface DocumentsResponse {
  count: number;
  documents: Document[];
  success: boolean;
  metadata: {
    filter_type: string;
    filter_value: string | null;
    limit: number;
  };
}

export interface ManagedUser {
  email: string;
  name: string;
  role: 'ADMIN' | 'GENAI' | 'DATABASE_MANAGEMENT' | 'DATA_ENGINEERING' | 'CLOUD' | 'MLOPS' | 'USER';
  roles: Array<'ADMIN' | 'GENAI' | 'DATABASE_MANAGEMENT' | 'DATA_ENGINEERING' | 'CLOUD' | 'MLOPS' | 'USER'>;
  business_unit: string | null;
  business_units: string[];
  employee_id?: number;
  email_verified?: boolean;
  status: 'active' | 'inactive' | 'pending_verification';
  created_at?: string;
  updated_at?: string;
}

class APIService {
  private async authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
    const token = localStorage.getItem('authToken');
    const headers = new Headers(init.headers || {});
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await globalThis.fetch(input, { ...init, headers });
    // A late response from an older session must not log out a new login.
    // Network failures and service outages (503) never invalidate credentials.
    if (response.status === 401 && token && token === localStorage.getItem('authToken')
        && !String(input).includes('/api/auth/login')) {
      localStorage.removeItem('authToken');
      localStorage.removeItem('authUser');
      window.dispatchEvent(new Event('sow-auth-expired'));
    }
    return response;
  }

  async fetchCustomTemplates(): Promise<any> {
    return this.makeRequest('/api/custom-templates', 'GET');
  }

  async extractCustomTemplate(file: File): Promise<{success: boolean; extraction_id?: string; status?: string; error?: string}> {
    const data = new FormData();
    data.append('template_file', file);
    const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL.replace(/\/$/, '')}/api/custom-templates/extract`, {
      method: 'POST',
      body: data,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Unable to extract custom template');
    return payload;
  }

  async fetchCustomTemplateExtraction(extractionId: string): Promise<any> {
    return this.makeRequest(`/api/custom-templates/extractions/${encodeURIComponent(extractionId)}`, 'GET');
  }

  async saveCustomTemplate(templateId: string, name: string): Promise<any> {
    return this.makeRequest(`/api/custom-templates/${encodeURIComponent(templateId)}/save`, 'POST', { name });
  }

  async deleteCustomTemplate(templateId: string): Promise<any> {
    return this.makeRequest(`/api/custom-templates/${encodeURIComponent(templateId)}`, 'DELETE');
  }

  async login(email: string, password: string): Promise<any> {
    const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Unable to sign in');
    return data;
  }

  async signup(data: {
    first_name: string; last_name: string; email: string; employee_id: number;
    business_unit: string; password: string; confirm_password: string;
  }): Promise<any> {
    const response = await globalThis.fetch(`${API_CONFIG.BASE_URL}/api/auth/signup`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    });
    const payload = await response.json();
    if (!response.ok) {
      const error = new Error(payload.error || 'Unable to create account') as Error & {
        verificationAttempted?: boolean;
      };
      error.verificationAttempted = Boolean(payload.verification_attempted);
      throw error;
    }
    return payload;
  }

  async verifyAccount(token: string): Promise<any> {
    const response = await globalThis.fetch(`${API_CONFIG.BASE_URL}/api/auth/verify`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Unable to verify account');
    return payload;
  }

  async resendVerification(email: string): Promise<any> {
    const response = await globalThis.fetch(`${API_CONFIG.BASE_URL}/api/auth/resend-verification`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Unable to resend verification');
    return payload;
  }

  async forgotPassword(email: string): Promise<any> {
    const response = await globalThis.fetch(`${API_CONFIG.BASE_URL}/api/auth/forgot-password`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Unable to request a password reset');
    return payload;
  }

  async requestPasswordChange(): Promise<{ success: boolean; message: string }> {
    return this.makeRequest('/api/auth/change-password-request', 'POST') as Promise<{
      success: boolean; message: string;
    }>;
  }

  async getCurrentUser(): Promise<{ success: boolean; user: any; business_units: string[] }> {
    return this.makeRequest('/api/auth/me', 'GET') as Promise<{
      success: boolean; user: any; business_units: string[];
    }>;
  }

  async resetPassword(data: {
    token: string; password: string; confirm_password: string;
  }): Promise<any> {
    const response = await globalThis.fetch(`${API_CONFIG.BASE_URL}/api/auth/reset-password`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Unable to reset password');
    return payload;
  }

  async fetchManagedUsers(): Promise<{ success: boolean; users: ManagedUser[]; business_units: string[] }> {
    return this.makeRequest('/api/admin/users', 'GET') as Promise<{ success: boolean; users: ManagedUser[]; business_units: string[] }>;
  }

  async createManagedUser(data: {
    email: string;
    name: string;
    role: ManagedUser['role'];
    roles?: ManagedUser['roles'];
    business_unit?: string | null;
    password: string;
    employee_id?: number;
  }): Promise<{ success: boolean; user: ManagedUser }> {
    return this.makeRequest('/api/admin/users', 'POST', data) as Promise<{ success: boolean; user: ManagedUser }>;
  }

  async updateManagedUser(
    email: string,
    data: Partial<Pick<ManagedUser, 'name' | 'role' | 'roles' | 'business_unit' | 'status'>> & { password?: string },
  ): Promise<{ success: boolean; user: ManagedUser }> {
    return this.makeRequest(`/api/admin/users/${encodeURIComponent(email)}`, 'PUT', data) as Promise<{ success: boolean; user: ManagedUser }>;
  }

  async deleteManagedUser(email: string): Promise<{ success: boolean }> {
    return this.makeRequest(`/api/admin/users/${encodeURIComponent(email)}`, 'DELETE') as Promise<{ success: boolean }>;
  }

  async fetchSowSections(): Promise<any> {
    return this.makeRequest('/api/sow-sections', 'GET');
  }

  async createSowSection(data: { label: string; prompt?: string; modes?: string[] }): Promise<any> {
    return this.makeRequest('/api/sow-sections', 'POST', data);
  }

  async updateSowSection(id: string, data: { label?: string; prompt?: string; modes?: string[] }): Promise<any> {
    return this.makeRequest(`/api/sow-sections/${encodeURIComponent(id)}`, 'PUT', data);
  }

  async deleteSowSection(id: string): Promise<any> {
    return this.makeRequest(`/api/sow-sections/${encodeURIComponent(id)}`, 'DELETE');
  }
  /**
   * Map internal mode values to API mode values
   */
  private mapModeToAPI(mode: 'poc' | 'production' | 'poc-to-production'): SOWMode {
    const modeMap: Record<string, SOWMode> = {
      'poc': 'POC',
      'production': 'PROD',
      'poc-to-production': 'POC_TO_PROD'
    };
    return modeMap[mode] || 'POC';
  }

  // ========================================================================
  // ACCOUNT MANAGEMENT APIs
  // ========================================================================

  /**
   * Fetch all accounts with optional filters
   */
  async fetchAccounts(params?: { segment?: string; priority?: string; limit?: number; business_unit?: string }): Promise<any> {
    try {
      const queryString = params ? '?' + new URLSearchParams(params as any).toString() : '';
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/accounts${queryString}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching accounts:', error);
      throw error;
    }
  }

  /**
   * Fetch account statistics
   */
  async fetchAccountStatistics(businessUnit?: string): Promise<any> {
    try {
      const query = businessUnit ? `?business_unit=${encodeURIComponent(businessUnit)}` : '';
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/accounts/statistics${query}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching account statistics:', error);
      throw error;
    }
  }

  /**
   * Fetch account by ID
   */
  async fetchAccount(accountId: string): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/accounts/${accountId}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching account:', error);
      throw error;
    }
  }

  /**
   * Create a new account
   */
  async createAccount(data: { account_name: string; segment: string; priority: string; description?: string; business_unit?: string }): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/accounts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      return await response.json();
    } catch (error) {
      console.error('Error creating account:', error);
      throw error;
    }
  }

  /**
   * Update an existing account
   */
  async updateAccount(accountId: string, data: { account_name: string; segment: string; priority: string; description?: string; business_unit?: string }): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/accounts/${accountId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates: data })
      });
      return await response.json();
    } catch (error) {
      console.error('Error updating account:', error);
      throw error;
    }
  }

  // ========================================================================
  // PROJECT MANAGEMENT APIs
  // ========================================================================

  /**
   * Fetch projects for an account
   */
  async fetchProjectsForAccount(accountId: string): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/accounts/${accountId}/projects`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching projects:', error);
      throw error;
    }
  }

  /**
   * Fetch project by ID
   */
  async fetchProject(projectId: string): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/projects/${projectId}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching project:', error);
      throw error;
    }
  }

  /**
   * Create a new project
   */
  async createProject(accountId: string, data: { project_name: string; description: string }): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/accounts/${accountId}/projects`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      return await response.json();
    } catch (error) {
      console.error('Error creating project:', error);
      throw error;
    }
  }

  /**
   * Delete an account
   */
  async deleteAccount(accountId: string): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/accounts/${accountId}`, {
        method: 'DELETE'
      });
      return await response.json();
    } catch (error) {
      console.error('Error deleting account:', error);
      throw error;
    }
  }

  /**
   * Delete a project
   */
  async deleteProject(projectId: string): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/projects/${projectId}`, {
        method: 'DELETE'
      });
      return await response.json();
    } catch (error) {
      console.error('Error deleting project:', error);
      throw error;
    }
  }

  // ========================================================================
  // SOW MANAGEMENT APIs
  // ========================================================================

  /**
   * Fetch SOWs for a project
   */
  async fetchSOWsForProject(projectId: string): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/projects/${projectId}/sows`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching SOWs:', error);
      throw error;
    }
  }

  /**
   * Create SOW for a project
   */
  async createSOWForProject(
    projectId: string,
    data: {
      mode: string;
      objective: string;
      customer_name?: string;
      project_name?: string;
      author_name?: string;
    }
  ): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/projects/${projectId}/sows`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      return await response.json();
    } catch (error) {
      console.error('Error creating SOW:', error);
      throw error;
    }
  }

  /**
   * Delete a SOW document
   */
  async deleteSOW(sowId: string): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/sows/${sowId}`, {
        method: 'DELETE'
      });
      return await response.json();
    } catch (error) {
      console.error('Error deleting SOW:', error);
      throw error;
    }
  }

  /**
   * Get all drafts for a project
   */
  async fetchDraftsForProject(projectId: string): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/projects/${projectId}/drafts`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching drafts:', error);
      throw error;
    }
  }

  /**
   * Get a specific draft
   */
  async fetchDraft(projectId: string, draftId: string): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/projects/${projectId}/drafts/${draftId}`);
      return await response.json();
    } catch (error) {
      console.error('Error fetching draft:', error);
      throw error;
    }
  }

  /**
   * Delete a draft
   */
  async deleteDraft(projectId: string, draftId: string): Promise<any> {
    try {
      const response = await this.authenticatedFetch(`${API_CONFIG.BASE_URL}/api/projects/${projectId}/drafts/${draftId}`, {
        method: 'DELETE'
      });
      return await response.json();
    } catch (error) {
      console.error('Error deleting draft:', error);
      throw error;
    }
  }

  /**
   * Generate SOW document via API
   */
  async generateSOW(
    authorName: string,
    companyName: string,
    mode: 'poc' | 'production' | 'poc-to-production',
    objective: string,
    projectName: string
  ): Promise<GenerateSOWResponse> {
    const apiMode = this.mapModeToAPI(mode);
    
    const requestData: GenerateSOWRequest = {
      author_name: authorName,
      company_name: companyName,
      mode: apiMode,
      objective: objective,
      project_name: projectName
    };


    try {
      const response = await this.makeRequest(
        API_CONFIG.ENDPOINTS.GENERATE_SOW,
        'POST',
        requestData
      );

      return response as GenerateSOWResponse;
    } catch (error) {
      console.error('Generate SOW Error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred'
      };
    }
  }

  /**
   * Convert POC to Production - fetches the existing POC file from s3_url and uploads it
   */
  async convertToProduction(
    authorName: string,
    companyName: string,
    projectName: string,
    s3Url: string,
    projectId?: string,
    accountId?: string
  ): Promise<GenerateSOWResponse> {
    try {
      const baseUrl = API_CONFIG.BASE_URL.replace(/\/$/, '');

      // Step 1: Download source POC document via proxy
      const proxyResponse = await this.authenticatedFetch(`${baseUrl}/api/proxy-download`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ s3_url: s3Url })
      });

      if (!proxyResponse.ok) {
        throw new Error(`Failed to fetch file via proxy: ${proxyResponse.statusText}`);
      }

      const fileBlob = await proxyResponse.blob();
      const urlParts = s3Url.split('/');
      const fileName = urlParts[urlParts.length - 1].split('?')[0] || 'document.docx';
      const file = new File([fileBlob], fileName, { type: fileBlob.type });

      // Step 2: Send to /api/preview — returns preview_id immediately (async generation)
      const formData = new FormData();
      formData.append('mode', 'POC_TO_PROD');
      formData.append('file', file);
      formData.append('company_name', companyName);
      formData.append('author_name', authorName);
      formData.append('project_name', projectName);
      if (projectId) formData.append('project_id', projectId);
      if (accountId) formData.append('account_id', accountId);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT);

      const previewResponse = await this.authenticatedFetch(`${baseUrl}/api/preview`, {
        method: 'POST',
        body: formData,
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!previewResponse.ok) {
        const errorText = await previewResponse.text();
        throw new Error(`HTTP ${previewResponse.status}: ${previewResponse.statusText} - ${errorText}`);
      }

      const previewData = await previewResponse.json();
      console.log('To Production Preview Response:', previewData);

      // Return the preview response — caller will poll status and show preview modal
      return previewData as GenerateSOWResponse;

    } catch (error) {
      console.error('To Production Error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred'
      };
    }
  }

  /**
   * Generate SOW document with file upload
   */
  async generateSOWWithFiles(files: File[]): Promise<GenerateSOWResponse> {
    try {
      const response = await this.makeRequestWithFiles(
        API_CONFIG.ENDPOINTS.GENERATE_SOW,
        'POST',
        files,
        'POC_TO_PROD'
      );

      return response as GenerateSOWResponse;
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred'
      };
    }
  }

  /**
   * Fetch all documents
   */
  async fetchDocuments(params?: { businessUnit?: string; mine?: boolean; limit?: number }): Promise<DocumentsResponse> {
    try {
      const search = new URLSearchParams();
      if (params?.businessUnit) search.set('business_unit', params.businessUnit);
      if (params?.mine) search.set('mine', 'true');
      if (params?.limit) search.set('limit', String(params.limit));
      const query = search.toString() ? `?${search.toString()}` : '';
      const response = await this.makeRequest(`/api/history${query}`, 'GET');
      return response as DocumentsResponse;
    } catch (error) {
      return {
        count: 0,
        documents: [],
        success: false,
        metadata: { filter_type: 'all', filter_value: null, limit: 100 }
      };
    }
  }

  async prepareSemanticIndex(): Promise<{ success: boolean; status?: string; remaining?: number }> {
    return this.makeRequest('/api/history/semantic-index', 'GET') as Promise<{
      success: boolean; status?: string; remaining?: number;
    }>;
  }

  async semanticSearchDocuments(query: string, params?: { mine?: boolean; limit?: number }): Promise<DocumentsResponse & { threshold?: number; indexing?: boolean; message?: string }> {
    const search = new URLSearchParams({ q: query });
    if (params?.mine) search.set('mine', 'true');
    if (params?.limit) search.set('limit', String(params.limit));
    return this.makeRequest(`/api/history/semantic-search?${search.toString()}`, 'GET') as Promise<DocumentsResponse & { threshold?: number; indexing?: boolean; message?: string }>;
  }

  async regenerateSOW(
    documentId: string,
    instructions: string,
    supportingDocs: File[] = [],
  ): Promise<GenerateSOWResponse> {
    const baseUrl = API_CONFIG.BASE_URL.replace(/\/$/, '');
    const formData = new FormData();
    formData.append('instructions', instructions);
    formData.append('supporting_doc_count', String(supportingDocs.length));
    supportingDocs.forEach(file => formData.append('supporting_docs', file));
    const response = await this.authenticatedFetch(
      `${baseUrl}/api/documents/${encodeURIComponent(documentId)}/regenerate`,
      { method: 'POST', body: formData },
    );
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      return { success: false, error: payload.error || `Regeneration failed (${response.status})` };
    }
    return payload as GenerateSOWResponse;
  }

  async fetchSourceDocuments(documentId: string): Promise<{ success: boolean; documents: SourceDocument[]; error?: string }> {
    try {
      return await this.makeRequest(
        `/api/documents/${encodeURIComponent(documentId)}/sources`,
        'GET',
      ) as { success: boolean; documents: SourceDocument[]; error?: string };
    } catch (error) {
      return { success: false, documents: [], error: error instanceof Error ? error.message : 'Unable to load documents' };
    }
  }

  async downloadSourceDocument(documentId: string, sourceId: string): Promise<Blob> {
    const baseUrl = API_CONFIG.BASE_URL.replace(/\/$/, '');
    const response = await this.authenticatedFetch(
      `${baseUrl}/api/documents/${encodeURIComponent(documentId)}/sources/${encodeURIComponent(sourceId)}`,
      { method: 'GET' },
    );
    if (!response.ok) throw new Error(`Supporting-document download failed (${response.status})`);
    return response.blob();
  }

  /**
   * Fetch recent POC documents
   */
  async fetchRecentPOCs(): Promise<DocumentsResponse> {
    try {
      const response = await this.makeRequest('/api/recent-pocs', 'GET');
      return response as DocumentsResponse;
    } catch (error) {
      return {
        count: 0,
        documents: [],
        success: false,
        metadata: { filter_type: 'recent-pocs', filter_value: null, limit: 100 }
      };
    }
  }

  /**
   * Fetch production documents
   */
  async fetchProductionRecords(): Promise<DocumentsResponse> {
    try {
      const response = await this.makeRequest('/api/recent-prod', 'GET');
      return response as DocumentsResponse;
    } catch (error) {
      return {
        count: 0,
        documents: [],
        success: false,
        metadata: { filter_type: 'production', filter_value: null, limit: 100 }
      };
    }
  }

  /**
   * Fetch POC to Production documents
   */
  async fetchPocToProductionRecords(): Promise<DocumentsResponse> {
    try {
      const response = await this.makeRequest('/api/recent-poc_to_prod', 'GET');
      return response as DocumentsResponse;
    } catch (error) {
      return {
        count: 0,
        documents: [],
        success: false,
        metadata: { filter_type: 'poc-to-production', filter_value: null, limit: 100 }
      };
    }
  }

  /**
   * Fetch companies grouped data
   */
  async fetchCompaniesGrouped(businessUnit?: string): Promise<any> {
    try {
      const query = businessUnit ? `?business_unit=${encodeURIComponent(businessUnit)}` : '';
      const response = await this.makeRequest(`/api/companies-grouped${query}`, 'GET');
      return response;
    } catch (error) {
      return { success: false, companies: [] };
    }
  }

  /**
   * Fetch company details
   */
  async fetchCompanyDetails(companyName: string): Promise<any> {
    try {
      const response = await this.makeRequest(`/api/company/${companyName.toUpperCase()}`, 'GET');
      return response;
    } catch (error) {
      return { success: false, data: null };
    }
  }

  async fetchProjectVersions(companyName: string, projectName: string): Promise<any> {
    try {
      const response = await this.makeRequest(
        `/api/company/${encodeURIComponent(companyName)}/project/${encodeURIComponent(projectName)}/data`,
        'GET'
      );
      return response;
    } catch (error) {
      return { success: false, data: null };
    }
  }

  /**
   * Generate preview
   */
  async generatePreview(
    authorName: string,
    companyName: string,
    mode: 'poc' | 'production' | 'poc-to-production',
    additionalDetails: string,
    projectName: string,
    file?: File,
    supportingDocs?: File[],
    projectId?: string,
    accountId?: string,
    selectedSowSections?: string[],
    businessUnit?: string,
    pricingOptions?: {
      region?: string;
      includeProposed?: boolean;
    },
    customTemplateId?: string,
    timelineFormat: 'table' | 'gantt' = 'table',
  ): Promise<any> {
    const apiMode = this.mapModeToAPI(mode);


    try {
      // poc-to-production requires file upload as FormData
      if (mode === 'poc-to-production' && file) {
        const baseUrl = API_CONFIG.BASE_URL.replace(/\/$/, '');
        const formData = new FormData();
        formData.append('mode', 'poc_to_prod');
        formData.append('timeline_format', timelineFormat);
        formData.append('file', file);
        formData.append('selected_sow_sections', JSON.stringify(selectedSowSections || []));
        if (customTemplateId) formData.append('custom_template_id', customTemplateId);
        if (businessUnit) formData.append('business_unit', businessUnit);
        if (pricingOptions?.region) formData.append('pricing_region', pricingOptions.region);
        formData.append('pricing_include_proposed', String(pricingOptions?.includeProposed ?? true));
        formData.append('pricing_read_cost', 'true');

        // Add supporting documents if provided
        if (supportingDocs && supportingDocs.length > 0) {
          supportingDocs.forEach(doc => {
            formData.append('supporting_docs', doc);
          });
          console.log(`Added ${supportingDocs.length} supporting document(s) to request`);
        }

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT);

        const response = await this.authenticatedFetch(`${baseUrl}/api/preview`, {
          method: 'POST',
          body: formData,
          signal: controller.signal
        });
        clearTimeout(timeoutId);

        const responseText = await response.text();
        console.log('Preview API Response (poc_to_prod):', responseText);

        try {
          return JSON.parse(responseText);
        } catch {
          return { success: false, error: 'Invalid JSON response' };
        }
      }

      // POC and Production modes — send as FormData fields with optional supporting docs
      const formData = new FormData();
      formData.append('author_name', authorName);
      formData.append('company_name', companyName);
      formData.append('mode', apiMode);
      formData.append('additional_details', additionalDetails);
      formData.append('project_name', projectName);
      formData.append('selected_sow_sections', JSON.stringify(selectedSowSections || []));
      if (customTemplateId) formData.append('custom_template_id', customTemplateId);
      if (businessUnit) formData.append('business_unit', businessUnit);
      if (pricingOptions?.region) formData.append('pricing_region', pricingOptions.region);
      formData.append('timeline_format', timelineFormat);
      formData.append('pricing_include_proposed', String(pricingOptions?.includeProposed ?? true));
      formData.append('pricing_read_cost', 'true');

      // Add project_id and account_id if provided (for linking to project)
      if (projectId) {
        formData.append('project_id', projectId);
        console.log('Including project_id in preview:', projectId);
      }
      if (accountId) {
        formData.append('account_id', accountId);
        console.log('Including account_id in preview:', accountId);
      }

      // Add supporting documents if provided
      if (supportingDocs && supportingDocs.length > 0) {
        supportingDocs.forEach(doc => {
          formData.append('supporting_docs', doc);
        });
        formData.append('supporting_doc_count', String(supportingDocs.length));
        console.log(`Added ${supportingDocs.length} supporting document(s) to request`);
      }

      const baseUrl = API_CONFIG.BASE_URL.replace(/\/$/, '');
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT);

      const response = await this.authenticatedFetch(`${baseUrl}/api/preview`, {
        method: 'POST',
        body: formData,
        signal: controller.signal
      });
      clearTimeout(timeoutId);

      const responseText = await response.text();
      console.log('Preview API Response:', responseText);

      try {
        const parsed = JSON.parse(responseText);
        if (supportingDocs && supportingDocs.length > 0) {
          const received = parsed.supporting_documents_received;
          const extracted = parsed.supporting_documents_extracted;
          if (received !== supportingDocs.length || extracted !== supportingDocs.length) {
            return {
              ...parsed,
              success: false,
              error: parsed.error || 'One or more supporting documents could not be read. Generation was stopped.',
            };
          }
        }
        return parsed;
      } catch {
        return { success: false, error: 'Invalid JSON response' };
      }
    } catch (error) {
      console.error('Preview API Error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred'
      };
    }
  }

  async recalculateAwsPricing(
    previewId: string,
    options: { region?: string; includeProposed?: boolean },
  ): Promise<any> {
    return this.makeRequest(
      `/api/preview/${encodeURIComponent(previewId)}/aws-pricing/recalculate`,
      'POST',
      {
        pricing_region: options.region || '',
        pricing_include_proposed: options.includeProposed ?? true,
        pricing_read_cost: true,
      },
    );
  }

  /**
   * Check preview status
   */
  async checkPreviewStatus(previewId: string): Promise<any> {
    console.log('Checking preview status for ID:', previewId);

    const endpoint = `/api/preview/status/${previewId}`;
    console.log('Status API URL:', `${API_CONFIG.BASE_URL}${endpoint}`);

    try {
      const response = await this.makeRequest(endpoint, 'GET');
      console.log('Preview Status Response:', response);
      return response;
    } catch (error) {
      console.error('Preview Status Error:', error);
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred'
      };
    }
  }

  async heartbeatPreview(previewId: string): Promise<any> {
    return this.makeRequest(`/api/preview/${encodeURIComponent(previewId)}/heartbeat`, 'POST', {});
  }

  async savePreviewAsDraft(previewId: string): Promise<any> {
    const endpoint = `/api/preview/${encodeURIComponent(previewId)}/draft`;
    const deadline = Date.now() + 10 * 60 * 1000;
    while (true) {
      const result = await this.makeRequest(endpoint, 'POST', {}) as any;
      if (!result.processing) return result;
      if (Date.now() >= deadline) {
        throw new Error('Draft save is still processing. Check SOW Records before trying again.');
      }
      await this.delay(2000);
    }
  }

  async discardPreview(previewId: string): Promise<any> {
    return this.makeRequest(`/api/preview/${encodeURIComponent(previewId)}`, 'DELETE');
  }

  async openDraftSOW(documentId: string): Promise<any> {
    return this.makeRequest(`/api/sows/${encodeURIComponent(documentId)}/draft/open`, 'POST', {});
  }

  async deleteDraftSOW(documentId: string): Promise<any> {
    return this.makeRequest(`/api/sows/${encodeURIComponent(documentId)}/draft`, 'DELETE');
  }

  /** Save XML and the current PNG export from the embedded draw.io editor. */
  async regenerateArchitecture(previewId: string, instructions: string): Promise<any> {
    return this.makeRequest(`/api/preview/${encodeURIComponent(previewId)}/architecture-regeneration`, 'POST', { instructions });
  }

  async architectureRegenerationStatus(previewId: string): Promise<any> {
    return this.makeRequest(`/api/preview/${encodeURIComponent(previewId)}/architecture-regeneration`, 'GET');
  }

  async updateArchitectureDiagram(previewId: string, drawioXml: string, imageData: string, diagramIndex = 0): Promise<any> {
    return this.makeRequest(
      `/api/preview/${encodeURIComponent(previewId)}/architecture-diagram`,
      'PUT',
      { drawio_xml: drawioXml, image_data: imageData, diagram_index: diagramIndex },
    );
  }

  /** Save reviewer-authored Markdown directly into the active preview. */
  async updatePreviewContent(previewId: string, content: Record<string, string>): Promise<any> {
    return this.makeRequest(
      `/api/preview/${encodeURIComponent(previewId)}/content`,
      'PUT',
      { content },
    );
  }

  /**
   * Get active in-memory previews (drafts) for a project
   */
  async fetchActivePreviewsForProject(projectId: string): Promise<any> {
    try {
      const response = await this.makeRequest(`/api/previews/active?project_id=${projectId}`, 'GET');
      return response;
    } catch (error) {
      console.error('Error fetching active previews:', error);
      return {
        success: false,
        previews: [],
        count: 0,
        error: error instanceof Error ? error.message : 'Unknown error occurred'
      };
    }
  }

  /**
   * Edit SOW document
   */
  async editSOW(
    previewId: string,
    selectedSections: string[],
    userInput: string,
    fullReplace: boolean = true
  ): Promise<any> {
    const requestData = {
      preview_id: previewId,
      selected_sections: selectedSections,
      user_input: userInput,
      full_replace: fullReplace  // Send as boolean, not string
    };

    console.log('Edit API Request:', requestData);

    try {
      const response = await this.makeRequestJSON('/api/edit', 'POST', requestData);
      return response;
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred'
      };
    }
  }

  /**
   * Finalize SOW document
   */
  async finalizeSOW(previewId: string): Promise<any> {
    const requestData = {
      preview_id: previewId
    };

    console.log('Finalize API Request:', requestData);

    try {
      // Retries may reach a still-running request. A 202 is not a saved SOW.
      const deadline = Date.now() + 10 * 60 * 1000;
      while (Date.now() < deadline) {
        const response: any = await this.makeRequestJSON('/api/finalize', 'POST', requestData);
        if (response.processing || response.status === 'processing') {
          await this.delay(2000);
          continue;
        }
        if (response.success && !(response.document_id && response.s3_url)) {
          throw new Error('Finalization did not return a downloadable document. Your preview has not been dismissed.');
        }
        return response;
      }
      throw new Error('Finalization is still running. Your draft remains available in SOW Records.');
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred'
      };
    }
  }

  /**
   * Fetch sections
   */
  async fetchSections(mode: 'poc' | 'prod' | 'poc_to_prod', previewId?: string): Promise<any> {
    try {
      const qs = previewId ? `?preview_id=${encodeURIComponent(previewId)}` : '';
      const response = await this.makeRequest(`/api/sections/${mode}${qs}`, 'GET');
      return response;
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred'
      };
    }
  }

  /**
   * Download document via S3 proxy (avoids Google Drive access issues)
   */
  async downloadDocument(s3Url: string, documentId?: string): Promise<Blob> {
    try {
      const baseUrl = API_CONFIG.BASE_URL.replace(/\/$/, '');
      const proxyUrl = `${baseUrl}/api/proxy-download`;

      console.log('Downloading via proxy:', proxyUrl);

      const response = await this.authenticatedFetch(proxyUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          s3_url: s3Url,
          document_id: documentId
        })
      });

      if (!response.ok) {
        throw new Error(`Failed to download: ${response.statusText}`);
      }

      const blob = await response.blob();
      if (!blob.size) throw new Error('The downloaded document is empty. No local file was written.');
      return blob;
    } catch (error) {
      console.error('Download error:', error);
      throw error;
    }
  }

  /**
   * Make HTTP request with JSON body
   */
  private async makeRequestJSON(
    endpoint: string,
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET',
    data?: unknown,
    attempt: number = 1
  ): Promise<unknown> {
    const baseUrl = API_CONFIG.BASE_URL.replace(/\/$/, '');
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${baseUrl}${cleanEndpoint}`;

    const options: RequestInit = {
      method,
      headers: {
        'Content-Type': 'application/json',
      },
    };

    if (data && (method === 'POST' || method === 'PUT')) {
      options.body = JSON.stringify(data);
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT);

      const response = await this.authenticatedFetch(url, {
        ...options,
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const responseData = await response.json();
      return responseData;
    } catch (error) {
      if (attempt < API_CONFIG.RETRY_ATTEMPTS && this.isRetryableError(error)) {
        await this.delay(API_CONFIG.RETRY_DELAY * attempt);
        return this.makeRequestJSON(endpoint, method, data, attempt + 1);
      }
      throw error;
    }
  }

  /**
   * Make HTTP request with file uploads
   */
  private async makeRequestWithFiles(
    endpoint: string,
    method: 'POST' | 'PUT',
    files: File[],
    mode: SOWMode,
    attempt: number = 1
  ): Promise<unknown> {
    const baseUrl = API_CONFIG.BASE_URL.replace(/\/$/, '');
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${baseUrl}${cleanEndpoint}`;

    const formData = new FormData();
    formData.append('mode', mode);
    
    files.forEach((file) => {
      formData.append(`file`, file);
    });

    const options: RequestInit = {
      method,
      body: formData
    };

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), API_CONFIG.TIMEOUT);

      const response = await this.authenticatedFetch(url, {
        ...options,
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const responseData = await response.json();
      return responseData;
    } catch (error) {
      if (attempt < API_CONFIG.RETRY_ATTEMPTS && this.isRetryableError(error)) {
        await this.delay(API_CONFIG.RETRY_DELAY * attempt);
        return this.makeRequestWithFiles(endpoint, method, files, mode, attempt + 1);
      }
      throw error;
    }
  }

  /**
   * Make HTTP request with retry logic
   */
  private async makeRequest(
    endpoint: string,
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' = 'GET',
    data?: unknown,
    attempt: number = 1
  ): Promise<unknown> {
    const baseUrl = API_CONFIG.BASE_URL.replace(/\/$/, '');
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${baseUrl}${cleanEndpoint}`;

    const options: RequestInit = { method };

    if (data && (method === 'POST' || method === 'PUT')) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(data);
    }

    // Use a shorter timeout for simple CRUD; keep the long one for generation endpoints
    const isGenerationEndpoint = endpoint.includes('/generate') || endpoint.includes('/preview') || endpoint.includes('/finalize');
    const timeout = isGenerationEndpoint ? API_CONFIG.TIMEOUT : API_CONFIG.FAST_TIMEOUT;

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), timeout);

      const response = await this.authenticatedFetch(url, {
        ...options,
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        let errorMessage = `HTTP ${response.status}: ${response.statusText}`;
        try {
          const errorText = await response.text();
          if (errorText) {
            try {
              const errorData = JSON.parse(errorText);
              if (errorData.message || errorData.error) {
                errorMessage = errorData.message || errorData.error;
              }
            } catch (e) {
              errorMessage = errorText;
            }
          }
        } catch (textError) {
          console.error('Error reading response text:', textError);
        }
        throw new Error(errorMessage);
      }

      const responseText = await response.text();
      
      if (!responseText || responseText.trim() === '') {
        return { success: false, error: 'Empty response from server' };
      }
      
      try {
        const responseData = JSON.parse(responseText);
        return responseData;
      } catch (jsonError) {
        return { success: false, error: 'Invalid JSON response', data: responseText };
      }
    } catch (error) {
      if (attempt < API_CONFIG.RETRY_ATTEMPTS && this.isRetryableError(error)) {
        await this.delay(API_CONFIG.RETRY_DELAY * attempt);
        return this.makeRequest(endpoint, method, data, attempt + 1);
      }
      throw error;
    }
  }

  /**
   * Check if error is retryable
   */
  private isRetryableError(error: unknown): boolean {
    if (error instanceof Error) {
      const message = error.message.toLowerCase();
      return (
        message.includes('network') ||
        message.includes('timeout') ||
        message.includes('aborted') ||
        message.includes('failed to fetch')
      );
    }
    return false;
  }

  /**
   * Utility function to delay execution
   */
  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

export default new APIService();
