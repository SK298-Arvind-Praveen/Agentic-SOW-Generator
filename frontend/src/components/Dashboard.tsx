import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { toast } from 'react-toastify';
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
  ArrowUpCircle,
  RefreshCw,
  X,
  Edit,
  BarChart3
} from 'lucide-react';
import SOWGenerator from './SOWGenerator';
import DatePicker from 'react-datepicker';
import 'react-datepicker/dist/react-datepicker.css';
import apiService, { Document } from '../services/apiService';
import { downloadWithNativeSaveAs } from '../utils/downloadFile';
import { latestDocumentForVersion, sortVersionKeysNewestFirst } from '../utils/versionOrdering';
import { formatTokenCount } from '../utils/tokenUsage';
import './Dashboard.css';
import './SOWGenerator.css';
import { BUSINESS_UNITS, useAuth } from '../contexts/AuthContext';

type SOWType = 'poc' | 'production' | 'poc-to-production';
type ViewType = 'generate' | 'records' | 'documents';

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAdmin, user } = useAuth();
  const selectableBusinessUnits = isAdmin ? BUSINESS_UNITS : (user?.business_units || []);
  const canSelectBusinessUnit = isAdmin || selectableBusinessUnits.length > 1;
  const [businessUnitFilter, setBusinessUnitFilter] = useState('');
  const [selectedSOW, setSelectedSOW] = useState<SOWType>('poc');
  const [selectedView, setSelectedView] = useState<ViewType>('generate');
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(false);
  const [recentPOCs, setRecentPOCs] = useState<Document[]>([]);
  const [isLoadingRecentPOCs, setIsLoadingRecentPOCs] = useState(false);
  const [productionRecords, setProductionRecords] = useState<Document[]>([]);
  const [isLoadingProductionRecords, setIsLoadingProductionRecords] = useState(false);
  const [pocToProductionRecords, setPocToProductionRecords] = useState<Document[]>([]);
  const [isLoadingPocToProductionRecords, setIsLoadingPocToProductionRecords] = useState(false);
  const [filters, setFilters] = useState({
    projectName: '',
    customerName: '',
    authorName: '',
    sowType: '',
    status: '',
    startDate: null as Date | null,
    endDate: null as Date | null
  });
  const [selectedCompany, setSelectedCompany] = useState<string | null>(null);
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [rowVersions, setRowVersions] = useState<{ [key: string]: Array<{ version: string; date: string; author: string; status: string; s3_url: string; total_tokens?: number | string }> }>({});
  const [recordsSearchQuery, setRecordsSearchQuery] = useState('');
  const [showRecordsFilter, setShowRecordsFilter] = useState(false);
  const [recordsFilterBy, setRecordsFilterBy] = useState<'company' | 'author'>('company');
  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' } | null>(null);
  const isFetchingRecords = useRef(false);
  const recordsCachedAt = useRef<number>(0);
  const RECORDS_CACHE_TTL = 60_000; // re-fetch at most once per 60s

  // To Production flow state
  const [isProductionLoading, setIsProductionLoading] = useState(false);
  const [productionProgress, setProductionProgress] = useState(0);
  const [productionTargetProgress, setProductionTargetProgress] = useState(0);
  const [showProductionPreviewModal, setShowProductionPreviewModal] = useState(false);
  const [productionPreviewData, setProductionPreviewData] = useState<any>(null);
  const [showProductionEditModal, setShowProductionEditModal] = useState(false);
  const [productionEditData, setProductionEditData] = useState<any>(null);
  const [productionSelectedSections, setProductionSelectedSections] = useState<string[]>([]);
  const [productionSectionInputs, setProductionSectionInputs] = useState<Record<string, string>>({});
  const [isProductionFullReplace, setIsProductionFullReplace] = useState(false);

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
        // Handle different date formats and field names
        const dateValue = doc.date || doc.created_at || doc.timestamp;
        if (dateValue) {
          try {
            // Try to format the date consistently
            const date = new Date(dateValue);
            return date.toLocaleDateString();
          } catch {
            return dateValue;
          }
        }
        return '';
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

 
  // Handle navigation state (e.g. redirect from /documents route)
  useEffect(() => {
    const state = location.state as { view?: ViewType } | null;
    if (state?.view) {
      setSelectedView(state.view);
      // Clear the state so it doesn't re-trigger on back navigation
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, []);

  // Fetch documents when documents view is selected
  useEffect(() => {
    if (selectedView === 'documents') {
      fetchDocuments();
    }
  }, [selectedView]);

  // Fetch records every time the records view is opened
  useEffect(() => {
    if (selectedView === 'records') {
      fetchAllRecords(true);
    }
  }, [selectedView, businessUnitFilter]);

  // Smooth progress animation for production loader
  useEffect(() => {
    if (!isProductionLoading) return;
    const interval = setInterval(() => {
      setProductionProgress(current => {
        if (current < productionTargetProgress) {
          return Math.min(current + 1, productionTargetProgress);
        }
        return current;
      });
    }, 200);
    return () => clearInterval(interval);
  }, [isProductionLoading, productionTargetProgress]);

  const fetchDocuments = async () => {
    setIsLoadingDocuments(true);
    const response = await apiService.fetchDocuments();
    if (response.success && response.documents && Array.isArray(response.documents)) {
      // Map the documents from the new API structure
      const mappedDocuments: Document[] = response.documents.map((item: any) => {
        // Extract document data from nested structure
        const doc = item.document || item;
        
        return {
          id: doc.document_id || doc.id,
          document_id: doc.document_id || doc.doc_id || doc.id,
          name: doc.project_name || doc.name || doc.title,
          company: doc.customer_name || doc.company || doc.company_name,
          author: doc.author_name || doc.author,
          date: doc.document_date || doc.date || doc.created_at || doc.timestamp?.split('T')[0],
          mode: doc.mode,
          project_name: doc.project_name || doc.name,
          company_name: doc.customer_name || doc.company,
          author_name: doc.author_name || doc.author,
          s3_url: doc.s3_url || doc.download_url || doc.url || '',
          drive_link: doc.drive_link,
          task_id: doc.task_id || item.task?.task_id,
          timestamp: doc.timestamp,
          version: doc.version,
          status: item.task?.status || doc.status,
          progress: item.task?.progress || doc.progress,
          current_step: item.task?.current_step || doc.current_step,
          is_processing: item.is_processing,
          total_tokens: doc.total_tokens,
        };
      });
      
      setDocuments(mappedDocuments);
    }
    setIsLoadingDocuments(false);
  };

  const fetchAllRecords = async (force = false) => {
    if (isFetchingRecords.current) return;
    if (!force && Date.now() - recordsCachedAt.current < RECORDS_CACHE_TTL) return;
    isFetchingRecords.current = true;
    try {
      const response = await apiService.fetchCompaniesGrouped(
        canSelectBusinessUnit && businessUnitFilter ? businessUnitFilter : undefined
      );
      if (!response?.success || !response.companies) return;

      const pocRecords: Document[] = [];
      const prodRecords: Document[] = [];
      const p2pRecords: Document[] = [];
      const newRowVersions: typeof rowVersions = {};

      Object.entries(response.companies).forEach(([, company]: [string, any]) => {
        const companyName = company.company_name;
        const docCount = company.document_count;
        if (!company.projects) return;

        Object.entries(company.projects).forEach(([projectName, projectData]: [string, any]) => {
          (['POC', 'PROD', 'POC_TO_PROD'] as const).forEach(mode => {
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
              date: doc.document_date || doc.timestamp?.split('T')[0] || 'N/A',
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
                  version: vk,
                  date: vDoc?.document_date || vDoc?.timestamp?.split('T')[0] || 'N/A',
                  author: vDoc?.author_name || 'N/A',
                  status: vDoc?.status || 'Completed',
                  s3_url: vDoc?.s3_url || vDoc?.drive_link || '',
                  total_tokens: vDoc?.total_tokens,
                };
              });
            }

            if (mode === 'POC') pocRecords.push(record);
            else if (mode === 'PROD') prodRecords.push(record);
            else if (mode === 'POC_TO_PROD') p2pRecords.push(record);
          });
        });
      });

      setRecentPOCs(pocRecords);
      setProductionRecords(prodRecords);
      setPocToProductionRecords(p2pRecords);
      setRowVersions(newRowVersions);
      recordsCachedAt.current = Date.now();
    } catch (error) {
      console.error('Error fetching grouped records:', error);
    } finally {
      isFetchingRecords.current = false;
    }
  };

  const fetchRecentPOCs = fetchAllRecords;
  const fetchProductionRecords = fetchAllRecords;
  const fetchPocToProductionRecords = fetchAllRecords;

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
    {
      id: 'poc-to-production' as SOWType,
      title: 'POC to Production',
      description: 'Statement of Work for transitioning POC to Production',
      icon: Database,
      color: '#7c3aed'
    }
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

   const getFilteredDocuments = () => {
    return documents.filter(doc => {
      const projectMatch = getDocumentProperty(doc, 'name').toLowerCase().includes(filters.projectName.toLowerCase());
      const customerMatch = getDocumentProperty(doc, 'company').toLowerCase().includes(filters.customerName.toLowerCase());
      const authorMatch = getDocumentProperty(doc, 'author').toLowerCase().includes(filters.authorName.toLowerCase());
      
      let sowTypeMatch = true;
      if (filters.sowType) {
        const docMode = getDocumentProperty(doc, 'mode').toLowerCase();
        sowTypeMatch = docMode === filters.sowType.toLowerCase() || 
                      (filters.sowType === 'poc' && docMode === 'poc') ||
                      (filters.sowType === 'prod' && (docMode === 'prod' || docMode === 'production')) ||
                      (filters.sowType === 'poc_to_prod' && (docMode === 'poc_to_prod' || docMode === 'poc-to-production'));
      }
      
      let statusMatch = true;
      if (filters.status) {
        const s3Url = getDocumentProperty(doc, 's3_url');
        if (filters.status === 'completed') {
          statusMatch = !!s3Url && !(doc.is_processing ?? false);
        } else if (filters.status === 'processing') {
          statusMatch = doc.is_processing ?? false;
        } else if (filters.status === 'pending') {
          statusMatch = !s3Url && !(doc.is_processing ?? false);
        }
      }
      
      let dateMatch = true;
      if (filters.startDate || filters.endDate) {
        const docDateStr = getDocumentProperty(doc, 'date');
        if (docDateStr) {
          const docDate = new Date(docDateStr);
          if (filters.startDate && docDate < filters.startDate) {
            dateMatch = false;
          }
          if (filters.endDate) {
            const endOfDay = new Date(filters.endDate);
            endOfDay.setHours(23, 59, 59, 999);
            if (docDate > endOfDay) {
              dateMatch = false;
            }
          }
        }
      }
      
      return projectMatch && customerMatch && authorMatch && sowTypeMatch && statusMatch && dateMatch;
    });
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

  const handleFilterChange = (field: string, value: string | Date | null) => {
    setFilters(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const getFilteredRecords = () => {
    if (selectedSOW === 'poc') {
      return recentPOCs;
    } else if (selectedSOW === 'production') {
      return productionRecords;
    } else if (selectedSOW === 'poc-to-production') {
      return pocToProductionRecords;
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

      // Extract filename from S3 URL or use project name
      const urlParts = s3Url.split('/');
      const s3Filename = urlParts[urlParts.length - 1].split('?')[0];
      const filename = s3Filename || `${projectName}.pdf`;
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

  const handleToProduction = async (record: Document) => {
    const companyName = record.company || record.company_name || record.customer_name || '';
    const projectName = record.name || record.project_name || record.title || '';
    const authorName = record.author || record.author_name || 'Unknown';
    const s3Url = record.s3_url || record.drive_link || '';

    if (!companyName || !projectName) {
      toast.error('Missing company or project information', { position: 'top-right', autoClose: 5000 });
      return;
    }

    if (!s3Url) {
      toast.error('No document file found for this POC record', { position: 'top-right', autoClose: 5000 });
      return;
    }

    // Reset and show loader
    setProductionPreviewData(null);
    setShowProductionPreviewModal(false);

    // Show non-blocking toast notification
    const toastId = toast.loading('Starting production conversion...', {
      position: 'bottom-right',
      autoClose: false,
    });

    try {
      const response = await apiService.convertToProduction(authorName, companyName, projectName, s3Url);

      if (response.success && (response as any).preview_id) {
        const previewId = (response as any).preview_id;
        localStorage.setItem('lastPreviewId', previewId);

        // Update toast to show background processing
        toast.update(toastId, {
          render: 'Converting in the background...',
          type: 'info',
          isLoading: true,
          autoClose: false,
          closeButton: false,
        });

        // Track progress with smart increments based on steps
        let currentProgressToast: any = toastId;
        const progressMap: { [key: string]: number } = {
          'Validating inputs': 10,
          'Extracting metadata': 15,
          'Retrieving RAG data': 20,
          'Retrieving POC RAG data': 20,
          'Retrieving PROD RAG data': 20,
          'Generating document': 30,
          'Researching': 35,
          'Research': 35,
          'Analyzing': 45,
          'Analyze': 45,
          'Validating': 55,
          'Validate': 55,
          'Generating content': 70,
          'Generate': 70,
          'Building document': 85,
          'Build': 85,
          'Document generated': 95,
          'Uploading': 98,
          'Completed': 100,
        };

        const getProgressFromStep = (step: string): number => {
          // Try exact match first
          if (progressMap[step]) return progressMap[step];

          // Try partial match
          for (const [key, value] of Object.entries(progressMap)) {
            if (step.toLowerCase().includes(key.toLowerCase())) {
              return value;
            }
          }

          // Default based on backend progress or 50%
          return 50;
        };

        const pollInterval = setInterval(async () => {
          try {
            const statusResponse = await apiService.checkPreviewStatus(previewId);

            // Calculate smart progress based on current step
            let displayProgress = statusResponse.progress || 50;
            if (statusResponse.current_step) {
              const stepProgress = getProgressFromStep(statusResponse.current_step);
              // Use the higher of backend progress or step-based progress
              displayProgress = Math.max(displayProgress, stepProgress);
            }

            // Update or create progress toast
            if (statusResponse.current_step) {
              const progressMessage = `Progress: ${displayProgress}% - ${statusResponse.current_step}`;

              if (currentProgressToast) {
                toast.update(currentProgressToast, {
                  render: progressMessage,
                  type: 'info',
                  isLoading: true,
                  autoClose: false,
                  closeButton: false,
                });
              } else {
                currentProgressToast = toast.info(progressMessage, {
                  position: 'bottom-right',
                  autoClose: false,
                  isLoading: true,
                  closeButton: false,
                });
              }
            }

            if (statusResponse.has_error || statusResponse.status === 'failed' || statusResponse.status === 'error') {
              clearInterval(pollInterval);
              toast.update(currentProgressToast, {
                render: `Conversion failed: ${statusResponse.error || statusResponse.message || 'Unknown error'}`,
                type: 'error',
                isLoading: false,
                autoClose: 8000,
                closeButton: true,
              });
              return;
            }

            if (statusResponse.status === 'completed' || statusResponse.status === 'success' || statusResponse.status === 'ready') {
              clearInterval(pollInterval);

              if (statusResponse.content || statusResponse.updated_content) {
                // Show success toast
                toast.update(currentProgressToast, {
                  render: 'Production conversion ready. Opening editor...',
                  type: 'success',
                  isLoading: false,
                  autoClose: 2000,
                  closeButton: true,
                });

                // Automatically set preview data and show modal
                setProductionPreviewData(statusResponse);
                setShowProductionPreviewModal(true);
              } else {
                toast.update(currentProgressToast, {
                  render: 'Conversion completed but no content is available',
                  type: 'warning',
                  isLoading: false,
                  autoClose: 5000,
                  closeButton: true,
                });
              }
            }
          } catch (err) {
            clearInterval(pollInterval);
            toast.update(currentProgressToast, {
              render: 'Failed to check conversion status',
              type: 'error',
              isLoading: false,
              autoClose: 5000,
              closeButton: true,
            });
          }
        }, 10000);

        setTimeout(() => {
          clearInterval(pollInterval);
          toast.warning('⏱️ Conversion timed out. Please try again.', {
            position: 'bottom-right',
            autoClose: 5000,
            closeButton: true,
          });
        }, 300000);
      } else {
        toast.update(toastId, {
          render: response.error || response.message || 'Failed to initiate production conversion',
          type: 'error',
          isLoading: false,
          autoClose: 5000,
          closeButton: true,
        });
      }
    } catch (error) {
      toast.update(toastId, {
        render: error instanceof Error ? error.message : 'Unknown error occurred',
        type: 'error',
        isLoading: false,
        autoClose: 5000,
        closeButton: true,
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

  const handleProductionEditFromPreview = async () => {
    const previewId = productionPreviewData?.preview_id || localStorage.getItem('lastPreviewId');
    if (!previewId) { toast.error('No preview ID found'); return; }

    setShowProductionPreviewModal(false);
    setProductionEditData(productionPreviewData);
    setProductionSelectedSections([]);
    setProductionSectionInputs({});
    setIsProductionFullReplace(false); // Reset toggle to Partial Edit mode
    setShowProductionEditModal(true);

    const toastId = toast.loading('Loading sections...', { position: 'top-right', autoClose: false });
    try {
      const sectionsResponse = await apiService.fetchSections('poc_to_prod');
      toast.update(toastId, { render: 'Sections loaded', type: 'success', isLoading: false, autoClose: 2000, closeButton: true });
    } catch {
      toast.update(toastId, { render: 'Failed to load sections', type: 'error', isLoading: false, autoClose: 3000, closeButton: true });
    }
  };

  const handleProductionSectionToggle = (section: string) => {
    setProductionSelectedSections(prev => {
      if (prev.includes(section)) {
        setProductionSectionInputs(prevInputs => { const n = { ...prevInputs }; delete n[section]; return n; });
        return prev.filter(s => s !== section);
      }
      return [...prev, section];
    });
  };

  const handleProductionSaveEdit = async () => {
    if (productionSelectedSections.length === 0) { toast.error('Please select at least one section to edit'); return; }
    const missing = productionSelectedSections.filter(s => !productionSectionInputs[s]?.trim());
    if (missing.length > 0) { toast.error(`Please provide input for: ${missing.join(', ')}`); return; }

    const previewId = productionEditData?.preview_id || localStorage.getItem('lastPreviewId');
    if (!previewId) { toast.error('No preview ID found'); return; }

    const toastId = toast.loading('Saving changes...', { position: 'top-right', autoClose: false });
    try {
      const combinedInput = productionSelectedSections.map(s => `[${s}]\n${productionSectionInputs[s]}`).join('\n\n');
      const response = await apiService.editSOW(previewId, productionSelectedSections, combinedInput, isProductionFullReplace);

      if (response.success) {
        toast.update(toastId, { render: `${productionSelectedSections.length} section(s) updated!`, type: 'success', isLoading: false, autoClose: 3000, closeButton: true });
        setShowProductionEditModal(false);
        setProductionPreviewData(response);
        setShowProductionPreviewModal(true);
        setProductionSelectedSections([]);
        setProductionSectionInputs({});
      } else {
        toast.update(toastId, { render: response.error || 'Failed to save changes', type: 'error', isLoading: false, autoClose: 5000, closeButton: true });
      }
    } catch (error) {
      toast.update(toastId, { render: 'Failed to save changes', type: 'error', isLoading: false, autoClose: 5000, closeButton: true });
    }
  };

  const handleProductionFinalize = async () => {
    const previewId = productionPreviewData?.preview_id || localStorage.getItem('lastPreviewId');
    if (!previewId) { toast.error('No preview ID found'); return; }

    setShowProductionPreviewModal(false);
    const toastId = toast.loading('Converting to Production...', { position: 'top-right', autoClose: false });
    try {
      const response = await apiService.finalizeSOW(previewId);
      if (response.success) {
        localStorage.removeItem('lastPreviewId');
        toast.update(toastId, { render: 'Successfully converted to Production!', type: 'success', isLoading: false, autoClose: 5000, closeButton: true });
        isFetchingRecords.current = false;
        fetchAllRecords();
      } else {
        toast.update(toastId, { render: response.error || 'Failed to convert to production', type: 'error', isLoading: false, autoClose: 5000, closeButton: true });
      }
    } catch (error) {
      toast.update(toastId, { render: error instanceof Error ? error.message : 'Unknown error', type: 'error', isLoading: false, autoClose: 5000, closeButton: true });
    }
  };

  const handleViewDocuments = () => {
    setSelectedView('documents');
    setSelectedCompany(null); // Reset company selection when switching to documents
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
          } else if (selectedSOW === 'poc-to-production') {
            modeData = projectData.POC_TO_PROD;
            modeKey = 'POC_TO_PROD';
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
                  date: doc.document_date || doc.timestamp?.split('T')[0] || 'N/A',
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
                      version: v,
                      date: vDoc?.document_date || vDoc?.timestamp?.split('T')[0] || 'N/A',
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
        } else if (selectedSOW === 'poc-to-production') {
          setPocToProductionRecords(companyRecords);
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

  const addNewVersion = (documentId: string) => {
    const currentVersions = rowVersions[documentId] || [];
    const newVersionNumber = `v${currentVersions.length + 1}.0`;
    const newVersion = {
      version: newVersionNumber,
      date: new Date().toISOString().split('T')[0],
      author: 'Current User',
      status: 'Draft',
      s3_url: ''
    };
    
    setRowVersions(prev => ({
      ...prev,
      [documentId]: [newVersion, ...currentVersions]
    }));
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
            <div className="dashboard-sow-tabs">
              {sowOptions.map((sow) => {
                const isActive = selectedSOW === sow.id && selectedView !== 'documents';
                return (
                  <button
                    key={sow.id}
                    className={`sow-tab ${isActive ? 'active' : ''}`}
                    onClick={() => handleSOWSelect(sow.id)}
                    title={sow.description}
                  >
                    {sow.title}
                  </button>
                );
              })}
              <button
                className={`sow-tab ${selectedView === 'documents' ? 'active' : ''}`}
                onClick={() => handleViewDocuments()}
                title="View all generated documents"
              >
                Documents
              </button>
            </div>
            {selectedView !== 'documents' && (
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
            <SOWGenerator selectedMode={selectedSOW} />
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
                  {canSelectBusinessUnit && (
                    <select
                      className="records-bu-filter"
                      value={businessUnitFilter}
                      onChange={(event) => {
                        recordsCachedAt.current = 0;
                        setBusinessUnitFilter(event.target.value);
                      }}
                      aria-label="Filter records by business unit"
                    >
                      <option value="">All Business Units</option>
                      {selectableBusinessUnits.map(unit => <option key={unit} value={unit}>{unit}</option>)}
                    </select>
                  )}
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
                  {(selectedSOW === 'poc' && isLoadingRecentPOCs) || 
                   (selectedSOW === 'production' && isLoadingProductionRecords) || 
                   (selectedSOW === 'poc-to-production' && isLoadingPocToProductionRecords) ? (
                    <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '40px' }}>
                      Loading companies...
                    </div>
                  ) : Object.keys(getCompanyGroups()).length > 0 ? (
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
                                  </div>
                                </td>
                              </tr>
                              {isExpanded && versions.map((version) => (
                                <tr key={`${documentId}-${version.version}`} className="version-history-row">
                                  <td aria-hidden="true"></td>
                                  <td>{getDocumentProperty(record, 'name')} - {version.version}</td>
                                  <td>{version.author}</td>
                                  <td>{version.date}</td>
                                  <td>{formatTokenCount(version.total_tokens)}</td>
                                  <td><span className="status-badge completed">Completed</span></td>
                                  <td style={{ textAlign: 'center' }}>
                                    <div className="action-buttons" style={{ justifyContent: 'center' }}>
                                      {version.s3_url ? (
                                        <button
                                          onClick={() => handleDownload({ s3_url: version.s3_url, project_name: version.version } as Document)}
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
          ) : (
            <div className="documents-view">
              <div className="documents-header">
                <h1>All Documents</h1>
                <p>View all generated SOW documents across all projects</p>
              </div>
              
              <div className="documents-table-container">
                <table className="documents-table">
                  <thead>
                    <tr>
                      <th>Project Name</th>
                      <th>Company Name</th>
                      <th>Author Name</th>
                      <th>SOW Type</th>
                      <th onClick={() => handleSort('date')} className="sortable-header">
                        <span className="header-content">
                          Generated Date
                          {renderSortIcon('date')}
                        </span>
                      </th>
                      <th>Status</th>
                      <th>Total Tokens</th>
                      <th>Actions</th>
                    </tr>
                    
<tr className="filter-row">
                      <th>
                        <input
                          type="text"
                          placeholder="Filter..."
                          value={filters.projectName}
                          onChange={(e) => handleFilterChange('projectName', e.target.value)}
                          className="filter-input"
                        />
                      </th>
                      <th>
                        <input
                          type="text"
                          placeholder="Filter..."
                          value={filters.customerName}
                          onChange={(e) => handleFilterChange('customerName', e.target.value)}
                          className="filter-input"
                        />
                      </th>
                      <th>
                        <input
                          type="text"
                          placeholder="Filter..."
                          value={filters.authorName}
                          onChange={(e) => handleFilterChange('authorName', e.target.value)}
                          className="filter-input"
                        />
                      </th>
                      <th>
                        <select
                          value={filters.sowType}
                          onChange={(e) => handleFilterChange('sowType', e.target.value)}
                          className="filter-input"
                        >
                          <option value="">All</option>
                          <option value="poc">POC</option>
                          <option value="prod">Production</option>
                          <option value="poc_to_prod">POC to Prod</option>
                        </select>
                      </th>
                      <th>
                        <div className="date-range-filter">
                          <DatePicker
                            selected={filters.startDate}
                            onChange={(date: Date | null) => handleFilterChange('startDate', date)}
                            placeholderText="From"
                            className="filter-input date-input"
                            dateFormat="dd-MM-yyyy"
                          />
                          <span className="date-separator">to</span>
                          <DatePicker
                            selected={filters.endDate}
                            onChange={(date: Date | null) => handleFilterChange('endDate', date)}
                            placeholderText="To"
                            className="filter-input date-input"
                            dateFormat="dd-MM-yyyy"
                          />
                        </div>
                      </th>
                      <th>
                        <select
                          value={filters.status}
                          onChange={(e) => handleFilterChange('status', e.target.value)}
                          className="filter-input"
                        >
                          <option value="">All</option>
                          <option value="completed">Completed</option>
                          <option value="processing">Processing</option>
                          <option value="pending">Pending</option>
                        </select>
                      </th>
                      <th></th>
                      <th></th>
                    </tr>

                  </thead>
                  <tbody>
                    {isLoadingDocuments ? (
                      <tr>
                        <td colSpan={8} className="no-records">
                          Loading documents...
                        </td>
                      </tr>
                    ) : getSortedRecords(getFilteredDocuments()).length > 0 ? (
                      getSortedRecords(getFilteredDocuments()).map((doc) => (
                        <tr key={getDocumentProperty(doc, 'document_id') || Math.random().toString()}>
                          <td>{getDocumentProperty(doc, 'name') || 'N/A'}</td>
                          <td>{getDocumentProperty(doc, 'company') || 'N/A'}</td>
                          <td>{getDocumentProperty(doc, 'author') || 'N/A'}</td>
                          <td>
                            <span className={`sow-type-badge ${getDocumentProperty(doc, 'mode').toLowerCase()}`}>
                              {(() => {
                                const mode = getDocumentProperty(doc, 'mode').toLowerCase();
                                if (mode === 'poc') return 'POC';
                                if (mode === 'prod' || mode === 'production') return 'Production';
                                if (mode === 'poc_to_prod' || mode === 'poc-to-production') return 'POC to Prod';
                                return mode || 'Unknown';
                              })()}
                            </span>
                          </td>
                          <td>{getDocumentProperty(doc, 'date') || 'N/A'}</td>
                          <td>
                            {doc.is_processing ? (
                              <span className="status-badge processing">
                                {doc.current_step || 'Processing'} {doc.progress ? `(${doc.progress}%)` : ''}
                              </span>
                            ) : getDocumentProperty(doc, 's3_url') ? (
                              <span className="status-badge completed">Completed</span>
                            ) : (
                              <span className="status-badge pending">Pending</span>
                            )}
                          </td>
                          <td>{formatTokenCount(doc.total_tokens)}</td>
                          <td>
                            <div className="action-buttons">
                              {getDocumentProperty(doc, 's3_url') && (
                                <a 
                                  href={getDocumentProperty(doc, 's3_url')} 
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="download-icon-btn"
                                  title="Download document"
                                >
                                  <Download width={"16px"} height={"16px"} className="download-icon" />
                                </a>
                              )}
                              {doc.is_processing && (
                                <button className="action-btn processing-btn" disabled>
                                  Processing...
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={8} className="no-records">
                          No documents found
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Production Preview Modal */}
      {showProductionPreviewModal && productionPreviewData && (
        <div className="modal-overlay" onClick={() => setShowProductionPreviewModal(false)}>
          <div className="modal-content modal-large preview-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>SOW Preview</h2>
              <button className="modal-close" onClick={() => setShowProductionPreviewModal(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body preview-body">
              <h3 className="preview-section-title">Document Information</h3>
              <div className="preview-info-grid">
                <div className="preview-info-row"><span className="preview-label">Mode:</span><span className="preview-value">{productionPreviewData.mode || 'N/A'}</span></div>
                <div className="preview-info-row"><span className="preview-label">Company Name:</span><span className="preview-value">{productionPreviewData.metadata?.company_name || productionPreviewData.company_name || 'N/A'}</span></div>
                <div className="preview-info-row"><span className="preview-label">Project Title:</span><span className="preview-value">{productionPreviewData.metadata?.project_title || productionPreviewData.project_title || 'N/A'}</span></div>
                <div className="preview-info-row"><span className="preview-label">Author Name:</span><span className="preview-value">{productionPreviewData.metadata?.author_name || productionPreviewData.author_name || 'N/A'}</span></div>
              </div>

              {productionPreviewData.content && (
                <>
                  <h3 className="preview-section-title">Generated Content</h3>
                  <div className="preview-content-display">
                    {typeof productionPreviewData.content === 'string' ? (
                      <pre className="preview-content-text">{productionPreviewData.content}</pre>
                    ) : (
                      <div className="preview-content-sections">
                        {Object.entries(productionPreviewData.content).map(([section, content]) => {
                          const isEdited = productionPreviewData.edited_sections?.includes(section);
                          return (
                            <div key={section} id={`prod-section-${section}`} className={`preview-content-section ${isEdited ? 'edited-section' : ''}`}>
                              <h4 className="preview-content-section-title">{section}{isEdited && <span className="edited-badge">Edited</span>}</h4>
                              <p className="preview-content-section-text">{String(content)}</p>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </>
              )}

              {productionPreviewData.updated_content && (
                <>
                  <h3 className="preview-section-title">Document Sections</h3>
                  <div className="preview-content-display">
                    <div className="preview-content-sections">
                      {Object.entries(productionPreviewData.updated_content).map(([section, content]) => {
                        const isEdited = productionPreviewData.edited_sections?.includes(section);
                        return (
                          <div key={section} id={`prod-section-${section}`} className={`preview-content-section ${isEdited ? 'edited-section' : ''}`}>
                            <h4 className="preview-content-section-title">{section}{isEdited && <span className="edited-badge">Edited</span>}</h4>
                            <p className="preview-content-section-text">{String(content)}</p>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </>
              )}
            </div>
            <div className="modal-footer">
              <button className="modal-btn modal-btn-secondary" onClick={() => setShowProductionPreviewModal(false)}>Close</button>
              <button className="modal-btn modal-btn-secondary" onClick={handleProductionEditFromPreview}>
                <Edit size={16} style={{ marginRight: '8px' }} />
                Edit Content
              </button>
              <button className="modal-btn modal-btn-primary" onClick={handleProductionFinalize}>
                <ArrowUpCircle size={16} style={{ marginRight: '8px' }} />
                To Production
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Production Edit Modal */}
      {showProductionEditModal && productionEditData && (
        <div className="modal-overlay" onClick={() => setShowProductionEditModal(false)}>
          <div className="modal-content modal-large edit-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Edit SOW Sections</h2>
              <button className="modal-close" onClick={() => setShowProductionEditModal(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body edit-body">
              {/* Edit Mode Toggle */}
              <div className="edit-mode-toggle-container" style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '16px',
                background: '#f9fafb',
                border: '1px solid #e5e7eb',
                borderRadius: '8px',
                marginBottom: '20px',
                gap: '16px',
                minHeight: '60px',
                width: '100%'
              }}>
                <div className="edit-mode-info" style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                  flex: 1
                }}>
                  <label className="edit-mode-label" style={{
                    fontSize: '14px',
                    fontWeight: 600,
                    color: '#374151',
                    margin: 0
                  }}>Edit Mode:</label>
                  <span className="edit-mode-description" style={{
                    fontSize: '13px',
                    color: '#6b7280',
                    lineHeight: 1.4
                  }}>
                    {isProductionFullReplace 
                      ? 'Full Edit - Completely replace section content' 
                      : 'Partial Edit - Make incremental changes to content'}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    console.log('Production Toggle clicked! Current state:', isProductionFullReplace);
                    setIsProductionFullReplace(!isProductionFullReplace);
                  }}
                  className={`toggle-button ${isProductionFullReplace ? 'active' : ''}`}
                  aria-pressed={isProductionFullReplace}
                  title={isProductionFullReplace ? 'Switch to Partial Edit' : 'Switch to Full Edit'}
                  style={{
                    position: 'relative',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '12px',
                    padding: isProductionFullReplace ? '8px 60px 8px 16px' : '8px 16px 8px 60px',
                    background: isProductionFullReplace ? '#dbeafe' : '#e5e7eb',
                    border: isProductionFullReplace ? '2px solid #3b82f6' : '2px solid #d1d5db',
                    borderRadius: '24px',
                    cursor: 'pointer',
                    fontSize: '14px',
                    fontWeight: 600,
                    color: isProductionFullReplace ? '#1e40af' : '#6b7280',
                    whiteSpace: 'nowrap'
                  }}
                >
                  <span className="toggle-slider" style={{
                    position: 'absolute',
                    left: isProductionFullReplace ? 'auto' : '4px',
                    right: isProductionFullReplace ? '4px' : 'auto',
                    width: '44px',
                    height: '28px',
                    background: isProductionFullReplace ? '#3b82f6' : '#9ca3af',
                    borderRadius: '20px',
                    boxShadow: 'inset 0 2px 4px rgba(0, 0, 0, 0.1)'
                  }}>
                    <span style={{
                      position: 'absolute',
                      top: '2px',
                      left: isProductionFullReplace ? '18px' : '2px',
                      width: '24px',
                      height: '24px',
                      background: 'white',
                      borderRadius: '50%',
                      boxShadow: '0 2px 4px rgba(0, 0, 0, 0.2)'
                    }}></span>
                  </span>
                  <span className="toggle-label" style={{ userSelect: 'none' }}>
                    {isProductionFullReplace ? 'Full Edit' : 'Partial Edit'}
                  </span>
                </button>
              </div>

              <div className="multi-section-selector">
                <label className="section-label">Select Sections to Edit:</label>
                <div className="sections-checkbox-list">
                  {Object.keys((productionEditData?.content || productionEditData?.updated_content) || {}).map((section) => (
                    <label key={section} className="section-checkbox-item">
                      <input
                        type="checkbox"
                        checked={productionSelectedSections.includes(section)}
                        onChange={() => handleProductionSectionToggle(section)}
                        className="section-checkbox"
                      />
                      <span className="section-checkbox-label">{section}</span>
                    </label>
                  ))}
                </div>
              </div>

              {productionSelectedSections.length > 0 && (
                <div className="selected-sections-inputs">
                  {productionSelectedSections.map((section) => (
                    <div key={section} className="section-input-group">
                      <div className="section-input-header">
                        <h4 className="section-input-title">{section}</h4>
                        <button type="button" onClick={() => handleProductionSectionToggle(section)} className="remove-section-btn" title="Remove section">
                          <X size={14} />
                        </button>
                      </div>
                      <div className="current-content-compact">
                        <span className="content-label">Current:</span>
                        <div className="content-preview">
                          {((productionEditData?.content || productionEditData?.updated_content)?.[section] || '').substring(0, 100)}...
                        </div>
                      </div>
                      <textarea
                        value={productionSectionInputs[section] || ''}
                        onChange={(e) => setProductionSectionInputs(prev => ({ ...prev, [section]: e.target.value }))}
                        placeholder={
                          isProductionFullReplace 
                            ? `Enter complete new content for ${section}...` 
                            : `Describe changes for ${section} (e.g., "Add another week in the timeline")...`
                        }
                        className="section-input-textarea"
                        rows={4}
                      />
                    </div>
                  ))}
                </div>
              )}

              {productionSelectedSections.length === 0 && (
                <div className="no-selection-message"><p>Please select at least one section to edit</p></div>
              )}
            </div>
            <div className="modal-footer">
              <button className="modal-btn modal-btn-secondary" onClick={() => setShowProductionEditModal(false)}>Close</button>
              <button className="modal-btn modal-btn-primary" onClick={handleProductionSaveEdit} disabled={productionSelectedSections.length === 0}>
                <Edit size={16} style={{ marginRight: '8px' }} />
                Save {productionSelectedSections.length > 0 && `(${productionSelectedSections.length})`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Production loader overlay */}
      {/* Removed blocking production loader - now using non-blocking toast notifications */}
    </>
  );
};

export default Dashboard;
