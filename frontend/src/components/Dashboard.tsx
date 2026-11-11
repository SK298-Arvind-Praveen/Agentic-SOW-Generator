import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from '../utils/toast';
import {
  FileText,
  Code,
  Plus,
  Database,
  ChevronDown,
  ChevronRight,
  Download,
  Search,
  Filter,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  RefreshCw,
  Trash2
} from 'lucide-react';
import SOWGenerator from './SOWGenerator';
import 'react-datepicker/dist/react-datepicker.css';
import apiService, { Document } from '../services/apiService';
import { downloadWithNativeSaveAs } from '../utils/downloadFile';
import { latestDocumentForVersion, sortVersionKeysNewestFirst } from '../utils/versionOrdering';
import { formatTokenCount } from '../utils/tokenUsage';
import { documentTimestamp, formatDocumentDateTime, sowDownloadFilename } from '../utils/documentPresentation';
import './Dashboard.css';
import './SOWGenerator.css';
import { useAuth } from '../contexts/AuthContext';
import SOWDeleteDialog from './SOWDeleteDialog';
import { usePageMemoryState } from '../hooks/usePageMemoryState';

type SOWType = 'poc' | 'production';
type ViewType = 'generate' | 'records';

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const { isAdmin, user } = useAuth();
  const [selectedSOW, setSelectedSOW] = usePageMemoryState<SOWType>(`sow-mode:${user?.email || 'anonymous'}`, 'poc');
  const [selectedView, setSelectedView] = useState<ViewType>('generate');
  const [recentPOCs, setRecentPOCs] = useState<Document[]>([]);
  const [productionRecords, setProductionRecords] = useState<Document[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [rowVersions, setRowVersions] = useState<{ [key: string]: Array<{ document_id?: string; version: string; date: string; author: string; status: string; s3_url: string; total_tokens?: number | string }> }>({});
  const [recordsSearchQuery, setRecordsSearchQuery] = useState('');
  const [showRecordsFilter, setShowRecordsFilter] = useState(false);
  const [recordsFilterBy, setRecordsFilterBy] = useState<'company' | 'author'>('company');
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' } | null>(null);
  const isFetchingRecords = useRef(false);
  const recordsCachedAt = useRef<number>(0);
  const RECORDS_CACHE_TTL = 60_000; // re-fetch at most once per 60s
  const [deleteTarget, setDeleteTarget] = useState<Document | null>(null);
  const [deletingSOW, setDeletingSOW] = useState(false);

  // Helper functions to safely access document properties
  const getDocumentProperty = (doc: Document, property: string): string => {
    if (!doc) return '';

    switch (property) {
      case 'author':
        return doc.author || doc.author_name || '';
      case 'company':
        return doc.company || doc.company_name || doc.customer_name || '';
      case 'name':
        return doc.name || doc.project_name || doc.title || '';
      case 'date':
        return formatDocumentDateTime(documentTimestamp(doc));
      case 'mode':
        return doc.mode || doc.sow_type || doc.type || '';
      case 'document_id':
        return doc.document_id || doc.doc_id || doc.id || '';
      case 's3_url':
        return doc.s3_url || doc.download_url || doc.url || doc.drive_link || '';
      default:
        return '';
    }
  };


  // Fetch records every time the records view is opened
  useEffect(() => {
    if (selectedView === 'records') {
      fetchAllRecords(true);
    }
  }, [selectedView]);

  const fetchAllRecords = async (force = false) => {
    if (isFetchingRecords.current) return;
    if (!force && Date.now() - recordsCachedAt.current < RECORDS_CACHE_TTL) return;
    isFetchingRecords.current = true;
    try {
      const response = await apiService.fetchCompaniesGrouped(
        undefined
      );
      if (!response?.success || !response.companies) return;

      const pocRecords: Document[] = [];
      const prodRecords: Document[] = [];
      const newRowVersions: typeof rowVersions = {};

      Object.entries(response.companies).forEach(([, company]: [string, any]) => {
        const companyName = company.company_name;
        const docCount = company.document_count;
        if (!company.projects) return;

        Object.entries(company.projects).forEach(([projectName, projectData]: [string, any]) => {
          (['POC', 'PROD'] as const).forEach(mode => {
            const versionMap = projectData[mode];
            if (!versionMap || typeof versionMap !== 'object') return;

            // Each key is a version string (v1, v2...), value is array of docs
            const versionKeys = sortVersionKeysNewestFirst(versionMap);
            if (versionKeys.length === 0) return;

            const latestKey = versionKeys[0];
            const latestDocs = versionMap[latestKey];
            const doc = latestDocumentForVersion(latestDocs);
            if (!doc) return;

            const docId = doc.document_id || `${companyName}-${projectName}-${latestKey}`;

            const record: Document = {
              id: docId,
              document_id: docId,
              name: doc.project_name || projectName,
              company: doc.customer_name || companyName,
              author: doc.author_name || 'N/A',
              date: documentTimestamp(doc) || 'N/A',
              mode,
              project_name: doc.project_name || projectName,
              company_name: doc.customer_name || companyName,
              author_name: doc.author_name || 'N/A',
              s3_url: doc.s3_url || doc.drive_link || '',
              version: latestKey,
              status: doc.status || 'Completed',
              task_id: doc.task_id,
              docCount,
              total_tokens: doc.total_tokens,
            };

            // Pre-load older versions for expand table
            if (versionKeys.length > 1) {
              newRowVersions[docId] = versionKeys.slice(1).map(vk => {
                const vDocs = versionMap[vk];
                const vDoc = latestDocumentForVersion(vDocs);
                return {
                  document_id: vDoc?.document_id,
                  version: vk,
                  date: documentTimestamp(vDoc || {}) || 'N/A',
                  author: vDoc?.author_name || 'N/A',
                  status: vDoc?.status || 'Completed',
                  s3_url: vDoc?.s3_url || vDoc?.drive_link || '',
                  total_tokens: vDoc?.total_tokens,
                };
              });
            }

            if (mode === 'POC') pocRecords.push(record);
            else if (mode === 'PROD') prodRecords.push(record);

          });
        });
      });

      setRecentPOCs(pocRecords);
      setProductionRecords(prodRecords);
      setRowVersions(newRowVersions);
      recordsCachedAt.current = Date.now();
    } catch (error) {
      console.error('Error fetching grouped records:', error);
    } finally {
      isFetchingRecords.current = false;
    }
  };

  const sowOptions = [
    {
      id: 'poc' as SOWType,
      title: 'SOW for POC',
      description: 'Statement of Work for Proof of Concept projects',
      icon: FileText,
      color: '#2563eb'
    },
    {
      id: 'production' as SOWType,
      title: 'SOW for Production',
      description: 'Statement of Work for Production-ready projects',
      icon: Code,
      color: '#059669'
    },

  ];

  const handleSOWSelect = (sowId: SOWType) => {
    setSelectedSOW(sowId);
    setSelectedView('generate');
    setSelectedCompany(null); // Reset company selection when changing SOW type
  };

  const handleViewSelect = (view: ViewType) => {
    setSelectedView(view);
    setSelectedCompany(null); // Reset company selection when changing views
  };

  const handleSort = (key: string) => {
    let direction: 'asc' | 'desc' = 'asc';

    if (sortConfig && sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }

    setSortConfig({ key, direction });
  };

  const getSortedRecords = (records: Document[]) => {
    if (!sortConfig) {
      return [...records].sort((a, b) => {
        const aDate = new Date(a.timestamp || a.created_at || a.date || 0).getTime();
        const bDate = new Date(b.timestamp || b.created_at || b.date || 0).getTime();
        return (Number.isFinite(bDate) ? bDate : 0) - (Number.isFinite(aDate) ? aDate : 0);
      });
    }

    const sortedRecords = [...records].sort((a, b) => {
      let aValue: any;
      let bValue: any;

      if (sortConfig.key === 'date') {
        aValue = new Date(getDocumentProperty(a, 'date') || 0).getTime();
        bValue = new Date(getDocumentProperty(b, 'date') || 0).getTime();
      } else if (sortConfig.key === 'project') {
        aValue = getDocumentProperty(a, 'name').toLowerCase();
        bValue = getDocumentProperty(b, 'name').toLowerCase();
      } else if (sortConfig.key === 'company') {
        aValue = getDocumentProperty(a, 'company').toLowerCase();
        bValue = getDocumentProperty(b, 'company').toLowerCase();
      } else if (sortConfig.key === 'author') {
        aValue = getDocumentProperty(a, 'author').toLowerCase();
        bValue = getDocumentProperty(b, 'author').toLowerCase();
      } else if (sortConfig.key === 'status') {
        aValue = (a.status || '').toLowerCase();
        bValue = (b.status || '').toLowerCase();
      } else {
        return 0;
      }

      if (aValue < bValue) {
        return sortConfig.direction === 'asc' ? -1 : 1;
      }
      if (aValue > bValue) {
        return sortConfig.direction === 'asc' ? 1 : -1;
      }
      return 0;
    });

    return sortedRecords;
  };

  const renderSortIcon = (columnKey: string) => {
    if (!sortConfig || sortConfig.key !== columnKey) {
      return <ArrowUpDown size={14} className="sort-icon-inactive" />;
    }
    return sortConfig.direction === 'asc'
      ? <ArrowUp size={14} className="sort-icon-active" />
      : <ArrowDown size={14} className="sort-icon-active" />;
  };

  const getFilteredRecords = () => {
    if (selectedSOW === 'poc') {
      return recentPOCs;
    } else if (selectedSOW === 'production') {
      return productionRecords;
    }
    return [];
  };

  /**
   * Handle document download via S3 proxy
   * This avoids Google Drive access permission issues
   */
  const handleDownload = async (record: Document) => {
    const s3Url = record.s3_url || record.download_url || record.url;
    const documentId = record.document_id || record.doc_id || record.id;
    const projectName = record.name || record.project_name || record.title || 'document';

    if (!s3Url) {
      toast.error('No download URL available for this document', {
        position: 'top-right',
        autoClose: 3000
      });
      return;
    }

    const toastId = toast.loading('Downloading document...', {
      position: 'top-right'
    });

    try {
      console.log('Downloading document:', { s3Url, documentId, projectName });

      const filename = sowDownloadFilename({ ...record, project_name: projectName });
      const saved = await downloadWithNativeSaveAs(
        () => apiService.downloadDocument(s3Url, documentId),
        filename,
      );

      toast.update(toastId, {
        render: saved ? 'Document downloaded successfully!' : 'Download cancelled',
        type: saved ? 'success' : 'info',
        isLoading: false,
        autoClose: 3000,
      });
    } catch (error) {
      console.error('Download error:', error);
      toast.update(toastId, {
        render: `Failed to download: ${error instanceof Error ? error.message : 'Unknown error'}`,
        type: 'error',
        isLoading: false,
        autoClose: 5000,
      });
    }
  };

  const handleRegenerate = (record: Document) => {
    const documentId = getDocumentProperty(record, 'document_id');
    if (!documentId) {
      toast.error('This record has no document identifier');
      return;
    }
    navigate(`/sow-records?regenerate=${encodeURIComponent(documentId)}`);
  };

  const deleteSOW = async () => {
    if (!deleteTarget || deletingSOW) return;
    const documentId = getDocumentProperty(deleteTarget, 'document_id');
    setDeletingSOW(true);
    try {
      const response = await apiService.deleteSOW(documentId);
      if (!response.success) throw new Error(response.error || 'Unable to delete SOW');
      setDeleteTarget(null);
      recordsCachedAt.current = 0;
      await fetchAllRecords(true);
      toast.success('SOW permanently deleted');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Unable to delete SOW');
    } finally {
      setDeletingSOW(false);
    }
  };

  // Group records by company
  const getCompanyGroups = () => {
    let records = getFilteredRecords();

    // Apply search filter
    if (recordsSearchQuery.trim()) {
      const query = recordsSearchQuery.toLowerCase();
      records = records.filter(record => {
        if (recordsFilterBy === 'company') {
          const company = getDocumentProperty(record, 'company') || '';
          return company.toLowerCase().includes(query);
        } else if (recordsFilterBy === 'author') {
          const author = getDocumentProperty(record, 'author') || '';
          return author.toLowerCase().includes(query);
        }
        return true;
      });
    }

    const groups: { [key: string]: Document[] } = {};

    records.forEach(record => {
      const company = getDocumentProperty(record, 'company') || 'Unknown Company';
      if (!groups[company]) {
        groups[company] = [];
      }
      groups[company].push(record);
    });

    return groups;
  };

  // Get company statistics
  const getCompanyStats = (records: Document[]) => {
    const totalRecords = records.length;
    const latestDate = records.reduce((latest, record) => {
      const recordDate = getDocumentProperty(record, 'date');
      return recordDate > latest ? recordDate : latest;
    }, '');

    return {
      total: totalRecords,
      latest: latestDate
    };
  };

  const handleCompanyCardClick = async (companyName: string) => {
    setSelectedCompany(companyName);

    // Fetch company details from API
    try {
      const response = await apiService.fetchCompanyDetails(companyName);
      console.log('Company Details Response:', response);

      if (response && response.success && response.projects) {
        const companyRecords: Document[] = [];

        // Iterate through projects
        Object.entries(response.projects).forEach(([projectName, projectData]: [string, any]) => {
          // Get the appropriate mode data based on selected SOW type
          let modeData: any = null;
          let modeKey = '';

          if (selectedSOW === 'poc') {
            modeData = projectData.POC;
            modeKey = 'POC';
          } else if (selectedSOW === 'production') {
            modeData = projectData.PROD;
            modeKey = 'PROD';
          }

          // If mode data exists, get only the latest version
          if (modeData && typeof modeData === 'object') {
            const versions = sortVersionKeysNewestFirst(modeData);
            if (versions.length > 0) {
              const latestVersion = versions[0];
              const documents = modeData[latestVersion];

              if (Array.isArray(documents) && documents.length > 0) {
              const doc = latestDocumentForVersion(documents);

                companyRecords.push({
                  id: doc.document_id || `${companyName}-${projectName}-${latestVersion}`,
                  document_id: doc.document_id,
                  name: doc.project_name || projectName,
                  company: doc.customer_name || companyName,
                  author: doc.author_name || 'N/A',
                  date: documentTimestamp(doc) || 'N/A',
                  mode: doc.mode || modeKey,
                  project_name: doc.project_name || projectName,
                  company_name: doc.customer_name || companyName,
                  s3_url: doc.s3_url || '',
                  task_id: doc.task_id,
                  timestamp: doc.timestamp,
                  version: latestVersion,
                  total_tokens: doc.total_tokens,
                });

                // Store other versions for expansion
                if (versions.length > 1) {
                  const otherVersions = versions.slice(1).map((v) => {
                    const versionDocs = modeData[v];
                    const vDoc = latestDocumentForVersion(versionDocs);
                    return {
                      document_id: vDoc?.document_id,
                      version: v,
                      date: documentTimestamp(vDoc || {}) || 'N/A',
                      author: vDoc?.author_name || 'N/A',
                      status: 'Completed',
                      s3_url: vDoc?.s3_url || vDoc?.drive_link || '',
                      total_tokens: vDoc?.total_tokens,
                    };
                  });

                  setRowVersions(prev => ({
                    ...prev,
                    [doc.document_id]: otherVersions
                  }));
                }
              }
            }
          }
        });

        // Update the appropriate state based on SOW type
        if (selectedSOW === 'poc') {
          setRecentPOCs(companyRecords);
        } else if (selectedSOW === 'production') {
          setProductionRecords(companyRecords);
        }
      }
    } catch (error) {
      console.error('Error fetching company details:', error);
    }
  };

  const handleBackToCompanies = () => {
    setSelectedCompany(null);
    isFetchingRecords.current = false;
    // Refetch the original data for the selected SOW type
    fetchAllRecords();
  };

  const toggleRowExpansion = (documentId: string, companyName: string, projectName: string) => {
    const newExpandedRows = new Set(expandedRows);
    if (newExpandedRows.has(documentId)) {
      newExpandedRows.delete(documentId);
    } else {
      newExpandedRows.add(documentId);
    }
    setExpandedRows(newExpandedRows);
  };

  return (
    <>
      <div className="main-content">
        <div className="content-header">
          <div className="header-left">
            <div className="header-title-section">
              <h1>SOW Creation System</h1>
            </div>
          </div>

          <div className="header-right">
            {(
              <div className="dashboard-view-tabs">
                <button
                  className={`view-tab ${selectedView === 'generate' ? 'active' : ''}`}
                  onClick={() => handleViewSelect('generate')}
                >
                  <Plus size={14} />
                  <span>Generate</span>
                </button>
                <button
                  className={`view-tab ${selectedView === 'records' ? 'active' : ''}`}
                  onClick={() => handleViewSelect('records')}
                >
                  <Database size={14} />
                  <span>Records</span>
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="content-body">
          {selectedView === 'generate' ? (
            <SOWGenerator selectedMode={selectedSOW} onModeChange={handleSOWSelect} />
          ) : selectedView === 'records' ? (
            <div className="records-view">
              <div className="records-header">
                <div className="records-header-left">
                  <h1>
                    {!selectedCompany ? (
                      // Show SOW type when viewing cards
                      `${sowOptions.find(s => s.id === selectedSOW)?.title} - SOW Records`
                    ) : (
                      // Show back arrow and selected company name when viewing details
                      <span style={{ display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }} onClick={handleBackToCompanies}>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: '#02adef' }}>
                          <line x1="19" y1="12" x2="5" y2="12"></line>
                          <polyline points="12 19 5 12 12 5"></polyline>
                        </svg>
                        <span>{selectedCompany} - SOW Records</span>
                      </span>
                    )}
                  </h1>
                  <p>View and manage your generated SOW documents</p>
                </div>
                <div className="records-header-right">
                  <div className="records-search-container">
                    <Search className="records-search-icon" size={14} />
                    <input
                      type="text"
                      placeholder={`Search by ${recordsFilterBy === 'company' ? 'company name' : 'author name'}...`}
                      className="records-search-input"
                      value={recordsSearchQuery}
                      onChange={(e) => setRecordsSearchQuery(e.target.value)}
                    />
                  </div>
                  <div className="records-filter-dropdown">
                    <button
                      className="records-filter-btn"
                      title="Filter"
                      onClick={() => setShowRecordsFilter(!showRecordsFilter)}
                    >
                      <Filter size={14} />
                    </button>
                    {showRecordsFilter && (
                      <div className="filter-dropdown-menu">
                        <div
                          className={`filter-option ${recordsFilterBy === 'company' ? 'active' : ''}`}
                          onClick={() => {
                            setRecordsFilterBy('company');
                            setShowRecordsFilter(false);
                          }}
                        >
                          Company Name
                        </div>
                        <div
                          className={`filter-option ${recordsFilterBy === 'author' ? 'active' : ''}`}
                          onClick={() => {
                            setRecordsFilterBy('author');
                            setShowRecordsFilter(false);
                          }}
                        >
                          Author Name
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {!selectedCompany ? (
                // Company Cards View
                <div className="company-cards-container">
                  {Object.keys(getCompanyGroups()).length > 0 ? (
                    Object.entries(getCompanyGroups()).map(([companyName, records]) => {
                      const stats = getCompanyStats(records);
                      const initials = companyName.split(' ').map(word => word[0]).join('').substring(0, 2).toUpperCase();
                      return (
                        <div
                          key={companyName}
                          className="company-card-pro"
                          onClick={() => handleCompanyCardClick(companyName)}
                        >
                          <div className="card-content-wrapper">
                            <div className="card-header-section">
                              <div className="company-icon-circle">
                                <span className="icon-text">{initials}</span>
                              </div>
                              <div className="company-header-info">
                                <div className="company-info-section">
                                  <h3 className="company-name-title">{companyName}</h3>
                                  {stats.latest && !isNaN(new Date(stats.latest).getTime()) && (
                                    <p className="company-subtitle">Updated {new Date(stats.latest).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</p>
                                  )}
                                </div>
                              </div>
                            </div>

                            <div className="card-metrics-grid">
                              <div className="metric-box">
                                <div className="metric-info">
                                  <div className="metric-label">Documents</div>
                                  <div className="metric-value">{records[0]?.docCount || stats.total}</div>
                                </div>
                                <div className="metric-icon">
                                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                                    <polyline points="14 2 14 8 20 8"></polyline>
                                  </svg>
                                </div>
                              </div>

                              <div className="metric-box">
                                <div className="metric-info">
                                  <div className="metric-label">Projects</div>
                                  <div className="metric-value">{records.length}</div>
                                </div>
                                <div className="metric-icon">
                                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                                  </svg>
                                </div>
                              </div>
                            </div>

                            <div className="card-footer-action">
                              <button className="view-btn-modern">
                                <span>View Details</span>
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                                  <polyline points="9 18 15 12 9 6"></polyline>
                                </svg>
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div style={{
                      gridColumn: '1 / -1',
                      textAlign: 'center',
                      padding: '80px 40px',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '20px'
                    }}>
                      <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="#d1d5db" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.6 }}>
                        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="9" y1="9" x2="15" y2="15"></line>
                        <line x1="15" y1="9" x2="9" y2="15"></line>
                      </svg>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <p style={{ margin: 0, fontSize: '18px', fontWeight: '600', color: '#374151' }}>
                          No companies found
                        </p>
                        <p style={{ margin: 0, fontSize: '14px', color: '#9ca3af' }}>
                          No records available for {sowOptions.find(s => s.id === selectedSOW)?.title}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                // Company Details Table View
                <div className="company-details-view">
                  <div className="records-table-container">
                    <table className="records-table">
                      <thead>
                        <tr>
                          <th style={{ width: '40px', textAlign: 'center' }}></th>
                          <th>Project Name</th>
                          <th>Author Name</th>
                          <th onClick={() => handleSort('date')} className="sortable-header">
                            <span className="header-content">
                              Date
                              {renderSortIcon('date')}
                            </span>
                          </th>
                          <th>Total Tokens</th>
                          <th>Status</th>
                          <th style={{ textAlign: 'center' }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {getSortedRecords(getCompanyGroups()[selectedCompany] || []).map((record) => {
                          const documentId = getDocumentProperty(record, 'document_id') || Math.random().toString();
                          const isExpanded = expandedRows.has(documentId);
                          const versions = rowVersions[documentId] || [];
                          const projectName = getDocumentProperty(record, 'name');

                          return (
                            <React.Fragment key={documentId}>
                              <tr>
                                <td style={{ textAlign: 'center' }}>
                                  <button
                                    onClick={() => toggleRowExpansion(documentId, selectedCompany || '', projectName)}
                                    style={{
                                      background: 'none',
                                      border: 'none',
                                      cursor: 'pointer',
                                      padding: '4px',
                                      display: 'flex',
                                      alignItems: 'center',
                                      justifyContent: 'center',
                                      borderRadius: '4px',
                                      transition: 'background-color 0.2s'
                                    }}
                                    onMouseEnter={(e) => {
                                      e.currentTarget.style.backgroundColor = '#f3f4f6';
                                    }}
                                    onMouseLeave={(e) => {
                                      e.currentTarget.style.backgroundColor = 'transparent';
                                    }}
                                  >
                                    {isExpanded ? (
                                      <ChevronDown size={16} color="#6b7280" />
                                    ) : (
                                      <ChevronRight size={16} color="#6b7280" />
                                    )}
                                  </button>
                                </td>
                                <td>{getDocumentProperty(record, 'name') || 'N/A'} - {record.version || 'v1'}</td>
                                <td>{getDocumentProperty(record, 'author') || 'N/A'}</td>
                                <td>{getDocumentProperty(record, 'date') || 'N/A'}</td>
                                <td>{formatTokenCount(record.total_tokens)}</td>
                                <td>
                                  {record.is_processing ? (
                                    <span className="status-badge processing">
                                      {record.current_step || 'Processing'} {record.progress ? `(${record.progress}%)` : ''}
                                    </span>
                                  ) : getDocumentProperty(record, 's3_url') ? (
                                    <span className="status-badge completed">Completed</span>
                                  ) : (
                                    <span className="status-badge pending">Pending</span>
                                  )}
                                </td>
                                <td>
                                  <div className="action-buttons" style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
                                    {getDocumentProperty(record, 's3_url') && (
                                      <button
                                        onClick={() => handleDownload(record)}
                                        className="download-icon-btn"
                                        title="Download document"
                                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center' }}
                                      >
                                        <Download width={"16px"} height={"16px"} className="download-icon" />
                                      </button>
                                    )}
                                    <button
                                      className="action-btn production-btn"
                                      onClick={() => handleRegenerate(record as any)}
                                      title="Regenerate and refine"
                                    >
                                      <RefreshCw width={"16px"} height={"16px"} />
                                    </button>
                                    {isAdmin && <button
                                      className="download-icon-btn sow-delete-icon"
                                      onClick={() => setDeleteTarget(record)}
                                      title="Permanently delete SOW"
                                    ><Trash2 width="16px" height="16px" /></button>}
                                  </div>
                                </td>
                              </tr>
                              {isExpanded && versions.map((version) => (
                                <tr key={`${documentId}-${version.version}`} className="version-history-row">
                                  <td aria-hidden="true"></td>
                                  <td>{getDocumentProperty(record, 'name')} - {version.version}</td>
                                  <td>{version.author}</td>
                                  <td>{formatDocumentDateTime(version.date)}</td>
                                  <td>{formatTokenCount(version.total_tokens)}</td>
                                  <td><span className="status-badge completed">Completed</span></td>
                                  <td style={{ textAlign: 'center' }}>
                                    <div className="action-buttons" style={{ justifyContent: 'center' }}>
                                      {version.s3_url ? (
                                        <button
                                          onClick={() => handleDownload({
                                            s3_url: version.s3_url,
                                            project_name: getDocumentProperty(record, 'name'),
                                            mode: record.mode,
                                            version: version.version,
                                          } as Document)}
                                          className="download-icon-btn"
                                          title={`Download ${version.version}`}
                                        >
                                          <Download width="16px" height="16px" className="download-icon" />
                                        </button>
                                      ) : (
                                        <span className="version-download-unavailable" title="No document available">
                                          <Download width="16px" height="16px" className="download-icon" />
                                        </span>
                                      )}
                                      {isAdmin && version.document_id && <button
                                        className="download-icon-btn sow-delete-icon"
                                        title={`Permanently delete ${version.version}`}
                                        onClick={() => setDeleteTarget({
                                          document_id: version.document_id,
                                          project_name: getDocumentProperty(record, 'name'),
                                          mode: record.mode,
                                          version: version.version,
                                        } as Document)}
                                      ><Trash2 width="16px" height="16px" /></button>}
                                    </div>
                                  </td>
                                </tr>
                              ))}
                            </React.Fragment>
                          );
                        }) || []}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </div>

      {deleteTarget && <SOWDeleteDialog
        name={`${getDocumentProperty(deleteTarget, 'name')} - ${deleteTarget.mode || ''} ${deleteTarget.version || ''}`.trim()}
        deleting={deletingSOW}
        onCancel={() => !deletingSOW && setDeleteTarget(null)}
        onConfirm={() => void deleteSOW()}
      />}
    </>
  );
};

export default Dashboard;
