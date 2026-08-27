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
  business_unit: string | null;
  status: 'active' | 'inactive';
  created_at?: string;
  updated_at?: string;
}

class APIService {
  private async authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
    const token = localStorage.getItem('authToken');
    const headers = new Headers(init.headers || {});
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await globalThis.fetch(input, { ...init, headers });
    if (response.status === 401 && !String(input).includes('/api/auth/login')) {
      localStorage.removeItem('authToken');
      localStorage.removeItem('authUser');
      window.dispatchEvent(new Event('sow-auth-expired'));
    }
    return response;
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

  async fetchManagedUsers(): Promise<{ success: boolean; users: ManagedUser[]; business_units: string[] }> {
    return this.makeRequest('/api/admin/users', 'GET') as Promise<{ success: boolean; users: ManagedUser[]; business_units: string[] }>;
  }

  async createManagedUser(data: {
    email: string;
    name: string;
    role: ManagedUser['role'];
    business_unit?: string | null;
    password: string;
  }): Promise<{ success: boolean; user: ManagedUser }> {
    return this.makeRequest('/api/admin/users', 'POST', data) as Promise<{ success: boolean; user: ManagedUser }>;
  }

  async updateManagedUser(
    email: string,
    data: Partial<Pick<ManagedUser, 'name' | 'role' | 'business_unit' | 'status'>> & { password?: string },
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
  async fetchDocuments(params?: { businessUnit?: string }): Promise<DocumentsResponse> {
    try {
      const query = params?.businessUnit
        ? `?business_unit=${encodeURIComponent(params.businessUnit)}`
        : '';
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
    objective: string,
    projectName: string,
    file?: File,
    supportingDocs?: File[],
    projectId?: string,
    accountId?: string,
    selectedSowSections?: string[],
    businessUnit?: string,
  ): Promise<any> {
    const apiMode = this.mapModeToAPI(mode);


    try {
      // poc-to-production requires file upload as FormData
      if (mode === 'poc-to-production' && file) {
        const baseUrl = API_CONFIG.BASE_URL.replace(/\/$/, '');
        const formData = new FormData();
        formData.append('mode', 'poc_to_prod');
        formData.append('file', file);
        formData.append('selected_sow_sections', JSON.stringify(selectedSowSections || []));
        if (businessUnit) formData.append('business_unit', businessUnit);

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
      formData.append('objective', objective);
      formData.append('project_name', projectName);
      formData.append('selected_sow_sections', JSON.stringify(selectedSowSections || []));
      if (businessUnit) formData.append('business_unit', businessUnit);

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
        return JSON.parse(responseText);
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

  /** Save XML and the current PNG export from the embedded draw.io editor. */
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
      const response = await this.makeRequestJSON('/api/finalize', 'POST', requestData);
      return response;
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
        let message = response.statusText || `HTTP ${response.status}`;
        try {
          const payload = await response.json();
          message = payload?.error || payload?.message || message;
        } catch {
          // Keep the HTTP status text when the server did not return JSON.
        }
        throw new Error(message);
      }

      return await response.blob();
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
