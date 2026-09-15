import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import {
  ChevronRight,
  Plus,
  FileText,
  Download,
  Calendar,
  User,
  ArrowLeft,
  Loader,
  RefreshCw,
  Trash2,
  AlertCircle,
  X,
  Edit,
  FileEdit
} from 'lucide-react';
import apiService from '../services/apiService';
import { downloadWithNativeSaveAs } from '../utils/downloadFile';
import { formatTokenCount } from '../utils/tokenUsage';
import { formatDocumentDateTime, sowDownloadFilename } from '../utils/documentPresentation';
import SOWGenerator from './SOWGenerator';
import './ProjectDetail.css';

interface SOW {
  sow_id: string;
  sow_db_id: string;
  mode: string;
  customer_name: string;
  project_name: string;
  drive_link: string;
  s3_url: string;
  linked_at: string;
  total_tokens?: number | string;
  version?: string;
}

interface Project {
  project_id: string;
  account_id: string;
  project_name: string;
  description: string;
  sow_count: number;
  created_at: string;
  status: string;
}

type SOWMode = 'POC' | 'PROD' | 'POC_TO_PROD';

const ProjectDetail: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [account, setAccount] = useState<any>(null);
  const [sows, setSOWs] = useState<SOW[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTab, setSelectedTab] = useState<SOWMode>('POC');
  const [showCreateSOW, setShowCreateSOW] = useState(false);
  const [showDeleteSOWModal, setShowDeleteSOWModal] = useState(false);
  const [sowToDelete, setSOWToDelete] = useState<SOW | null>(null);
  const [activePreviews, setActivePreviews] = useState<any[]>([]);
  const [showDraftsModal, setShowDraftsModal] = useState(false);
  const [selectedDraft, setSelectedDraft] = useState<any | null>(null);

  // Polling state for auto-refresh after SOW creation
  const [isPolling, setIsPolling] = useState(false);
  const [pollCount, setPollCount] = useState(0);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const initialSOWCount = useRef<number>(0);
  const pollCountRef = useRef<number>(0);         // ref so interval always reads current value
  const pollingModeRef = useRef<SOWMode | null>(null); // track which mode we're polling for

  useEffect(() => {
    if (projectId) {
      fetchProjectDetails();
      fetchActivePreviews();
    }
  }, [projectId]);

  const fetchProjectDetails = async () => {
    try {
      setLoading(true);

      console.log('Fetching project:', projectId);

      // Fetch project details
      const projectResponse = await apiService.fetchProject(projectId!);
      console.log('Project response:', projectResponse);

      if (projectResponse.success && projectResponse.project) {
        setProject(projectResponse.project);

        // Fetch account details
        const accountId = projectResponse.project.account_id;
        console.log('Fetching account:', accountId);

        const accountResponse = await apiService.fetchAccount(accountId);
        console.log('Account response:', accountResponse);

        if (accountResponse.success && accountResponse.account) {
          setAccount(accountResponse.account);
        }

        // Fetch SOWs for this project
        const sowsResponse = await apiService.fetchSOWsForProject(projectId!);
        console.log('SOWs response:', sowsResponse);

        if (sowsResponse.success) {
          setSOWs(sowsResponse.sows || []);
        }
      } else {
        console.error('Project not found in response:', projectResponse);
        toast.error('Project not found. Please check if the project exists.');
      }
    } catch (error) {
      toast.error('Failed to fetch project details');
      console.error('Error fetching project:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchActivePreviews = async () => {
    try {
      console.log('Fetching active previews for project:', projectId);
      const response = await apiService.fetchActivePreviewsForProject(projectId!);

      if (response.success) {
        setActivePreviews(response.previews || []);
        console.log(`Found ${response.count} active preview drafts`);
      }
    } catch (error) {
      console.error('Error fetching active previews:', error);
    }
  };

  const getFilteredSOWs = () => {
    return sows.filter(sow => sow.mode === selectedTab);
  };

  const handleCreateSOW = () => {
    setShowCreateSOW(true);
  };

  // Start polling for new SOWs after creation
  const startPolling = (targetMode?: SOWMode) => {
    // Clear any existing interval first
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }

    initialSOWCount.current = sows.length;
    pollCountRef.current = 0;
    pollingModeRef.current = targetMode || null;
    setIsPolling(true);
    setPollCount(0);

    console.log(`Starting polling for new SOWs (mode: ${targetMode || 'any'}, initial: ${sows.length})`);

    // Poll every 10 seconds, max 36 times (6 minutes)
    pollingIntervalRef.current = setInterval(async () => {
      pollCountRef.current += 1;
      const currentCount = pollCountRef.current;
      setPollCount(currentCount);
      console.log(`📡 Polling attempt ${currentCount}/36 for project ${projectId}`);

      try {
        const sowsResponse = await apiService.fetchSOWsForProject(projectId!);

        if (sowsResponse.success) {
          const newSOWs: SOW[] = sowsResponse.sows || [];
          console.log(`📊 Fetched ${newSOWs.length} SOWs (initial: ${initialSOWCount.current})`);

          // Detect new SOW: either total count increased, or mode-specific count increased
          const modeSOWs = pollingModeRef.current
            ? newSOWs.filter(s => s.mode === pollingModeRef.current)
            : newSOWs;
          const initModeCount = pollingModeRef.current
            ? sows.filter(s => s.mode === pollingModeRef.current).length
            : initialSOWCount.current;

          if (newSOWs.length > initialSOWCount.current || modeSOWs.length > initModeCount) {
            console.log('New SOW detected');
            setSOWs(newSOWs);

            if (project) {
              setProject({ ...project, sow_count: newSOWs.length });
            }

            toast.success('New SOW document is ready!', {
              position: 'top-right',
              autoClose: 5000,
            });
            stopPolling();
            return;
          }
        }
      } catch (error) {
        console.error('Polling error:', error);
      }

      // Stop after 6 minutes (36 polls × 10 seconds) — use ref, not state
      if (pollCountRef.current >= 36) {
        console.log('⏱️ Polling timeout - stopping');
        stopPolling();
        toast.info('Generation is taking longer than expected. Click Refresh to check for updates.', {
          position: 'top-right',
          autoClose: 8000,
        });
      }
    }, 10000);
  };

  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    pollCountRef.current = 0;
    pollingModeRef.current = null;
    setIsPolling(false);
    setPollCount(0);
    console.log('⏹️ Stopped polling');
  };

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, []);

  const handleDeleteSOWClick = (sow: SOW, e: React.MouseEvent) => {
    e.stopPropagation();
    setSOWToDelete(sow);
    setShowDeleteSOWModal(true);
  };

  const handleDeleteSOWConfirm = async () => {
    if (!sowToDelete) return;

    try {
      const response = await apiService.deleteSOW(sowToDelete.sow_db_id);
      if (response.success) {
        toast.success('SOW deleted successfully!');
        setShowDeleteSOWModal(false);
        setSOWToDelete(null);
        fetchProjectDetails();
      } else {
        toast.error(response.error || 'Failed to delete SOW');
      }
    } catch (error) {
      toast.error('Failed to delete SOW');
      console.error('Error deleting SOW:', error);
    }
  };

  const handleSOWCreated = () => {
    setShowCreateSOW(false);
    toast.success('SOW generation started! Checking for updates...', {
      position: 'top-right',
      autoClose: 5000,
    });

    // Start polling for new SOWs in the current tab's mode
    startPolling(selectedTab as SOWMode);
  };

  // Manual refresh handler
  const handleRefresh = async () => {
    console.log('Manual refresh triggered');
    await fetchProjectDetails();
    toast.info('Refreshed SOW list', {
      position: 'top-right',
      autoClose: 2000,
    });
  };

  // Handle SOW download via S3 proxy
  const handleDownloadSOW = async (sow: SOW) => {
    const s3Url = sow.s3_url || sow.drive_link;

    if (!s3Url) {
      toast.error('No download URL available for this SOW', {
        position: 'top-right',
        autoClose: 3000,
      });
      return;
    }

    const toastId = toast.loading('Downloading SOW document...', {
      position: 'top-right',
    });

    try {
      console.log('Downloading SOW:', { s3Url, sow_id: sow.sow_id, project: sow.project_name });

      const filename = sowDownloadFilename(sow);
      const saved = await downloadWithNativeSaveAs(
        () => apiService.downloadDocument(s3Url, sow.sow_id),
        filename,
      );

      toast.update(toastId, {
        render: saved ? 'SOW document downloaded successfully!' : 'Download cancelled',
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

  const formatDate = (dateString: string) => {
    return formatDocumentDateTime(dateString);
  };

  const handleRegenerateSOW = (sow: SOW, e: React.MouseEvent) => {
    e.stopPropagation();
    const documentId = sow.sow_db_id || sow.sow_id;
    if (!documentId) {
      toast.error('This SOW has no document identifier');
      return;
    }
    navigate(`/sow-records?regenerate=${encodeURIComponent(documentId)}`);
  };

  // Handle opening drafts modal
  const handleShowDrafts = () => {
    fetchActivePreviews(); // Refresh drafts list
    setShowDraftsModal(true);
  };

  // Handle continuing a draft (redirect to SOW creation with preview_id)
  const handleContinueDraft = (draft: any) => {
    setSelectedDraft(draft);
    setShowDraftsModal(false);

    console.log('📝 Continuing draft:', draft);

    // Store preview_id in localStorage so SOWGenerator can load it
    localStorage.setItem('lastPreviewId', draft.preview_id);

    // Store flag to indicate we're loading from draft
    localStorage.setItem('loadingFromDraft', 'true');

    toast.info(`📝 Loading draft: ${draft.metadata.project_title}`, {
      position: 'top-right',
      autoClose: 3000,
    });

    // Navigate to SOW creation - SOWGenerator will automatically load the preview
    setShowCreateSOW(true);
  };

  const getModeLabel = (mode: string) => {
    switch (mode) {
      case 'POC':
        return 'SOW for POC';
      case 'PROD':
        return 'SOW for Production';
      case 'POC_TO_PROD':
        return 'POC to Production';
      default:
        return mode;
    }
  };

  const getModeColor = (mode: string) => {
    switch (mode) {
      case 'POC':
        return '#2563eb';
      case 'PROD':
        return '#059669';
      case 'POC_TO_PROD':
        return '#7c3aed';
      default:
        return '#6b7280';
    }
  };

  if (loading) {
    return (
      <div className="project-detail-loading">
        <div className="spinner"></div>
        <p>Loading project details...</p>
      </div>
    );
  }

  if (!project) {
    return (
      <div className="project-detail-error">
        <p>Project not found</p>
        <button onClick={() => navigate('/accounts')}>Back to Accounts</button>
      </div>
    );
  }

  // If showing SOW creation form
  if (showCreateSOW) {
    // Map tab to mode
    const modeMap: { [key: string]: 'poc' | 'production' | 'poc-to-production' } = {
      'POC': 'poc',
      'PROD': 'production',
      'POC_TO_PROD': 'poc-to-production'
    };

    console.log('=== ProjectDetail - SOW Form Debug ===');
    console.log('Full account object:', account);
    console.log('account.account_name:', account?.account_name);
    console.log('project.project_name:', project.project_name);
    console.log('projectId:', projectId);
    console.log('Passing accountName to SOWGenerator:', account?.account_name || 'EMPTY!');

    // Don't render form until account data is loaded
    if (!account || !account.account_name) {
      return (
        <div className="project-detail-page">
          <div className="sow-creation-header">
            <button onClick={() => setShowCreateSOW(false)} className="back-to-project-btn">
              <ArrowLeft size={20} />
              <span>Back to Project</span>
            </button>
            <div className="sow-creation-title">
              <h1>Create {getModeLabel(selectedTab)}</h1>
            </div>
          </div>
          <div className="sow-generator-wrapper">
            <div className="project-detail-loading">
              <div className="spinner"></div>
              <p>Loading account information...</p>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="project-detail-page">
        {/* Header with back button */}
        <div className="sow-creation-header">
          <button onClick={() => setShowCreateSOW(false)} className="back-to-project-btn">
            <ArrowLeft size={20} />
            <span>Back to Project</span>
          </button>
          <div className="sow-creation-title">
            <h1>Create {getModeLabel(selectedTab)}</h1>
            <p>Account: {account.account_name} | Project: {project.project_name}</p>
          </div>
        </div>

        {/* SOW Generator - Full Form */}
        <div className="sow-generator-wrapper">
          {account && account.account_name ? (
            <SOWGenerator
              selectedMode={modeMap[selectedTab]}
              projectId={projectId}
              projectName={project.project_name}
              accountName={account.account_name}
              accountId={project.account_id}
              onSuccess={handleSOWCreated}
              onCancel={() => setShowCreateSOW(false)}
            />
          ) : (
            <div className="loading-account">
              <div className="spinner"></div>
              <p>Loading account information for auto-population...</p>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="project-detail-page">
      {/* Breadcrumb */}
      <div className="breadcrumb">
        <button onClick={() => navigate('/accounts')} className="breadcrumb-link">
          Accounts
        </button>
        <ChevronRight size={16} className="breadcrumb-separator" />
        <button onClick={() => navigate(`/accounts/${project.account_id}`)} className="breadcrumb-link">
          {account?.account_name || 'Account'}
        </button>
        <ChevronRight size={16} className="breadcrumb-separator" />
        <span className="breadcrumb-current">{project.project_name}</span>
      </div>

      {/* Project Header */}
      <div className="project-header-detail">
        <div className="project-header-left">
          <button onClick={() => navigate(`/accounts/${project.account_id}`)} className="back-button">
            <ArrowLeft size={16} />
          </button>
          <div className="project-avatar">
            {project.project_name.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <h1>{project.project_name}</h1>
            {project.description && <p>{project.description}</p>}
            <div className="project-meta">
              <span className="meta-item">
                <Calendar size={12} />
                Created {formatDate(project.created_at)}
              </span>
              <span className="meta-item">
                <FileText size={12} />
                {project.sow_count} SOW{project.sow_count !== 1 ? 's' : ''}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="sow-tabs">
        <button
          className={`tab-button ${selectedTab === 'POC' ? 'active' : ''}`}
          onClick={() => setSelectedTab('POC')}
        >
          <FileText size={15} />
          <span>SOW for POC</span>
          <span className="tab-count">{sows.filter(s => s.mode === 'POC').length}</span>
        </button>

        <button
          className={`tab-button ${selectedTab === 'PROD' ? 'active' : ''}`}
          onClick={() => setSelectedTab('PROD')}
        >
          <FileText size={15} />
          <span>SOW for Production</span>
          <span className="tab-count">{sows.filter(s => s.mode === 'PROD').length}</span>
        </button>

        <button
          className={`tab-button ${selectedTab === 'POC_TO_PROD' ? 'active' : ''}`}
          onClick={() => setSelectedTab('POC_TO_PROD')}
        >
          <FileText size={15} />
          <span>POC to Production</span>
          <span className="tab-count">{sows.filter(s => s.mode === 'POC_TO_PROD').length}</span>
        </button>
      </div>

      {/* SOWs Content */}
      <div className="sows-content">
        <div className="sows-header">
          <h2>{getModeLabel(selectedTab)}</h2>
          <div className="sows-header-actions">
            {activePreviews.length > 0 && (
              <button
                className="drafts-btn"
                onClick={handleShowDrafts}
                title="View in-memory preview drafts"
              >
                <FileEdit size={18} />
                Drafts ({activePreviews.length})
              </button>
            )}
            <button
              className="refresh-sow-btn"
              onClick={handleRefresh}
              disabled={loading || isPolling}
              title={isPolling ? `Checking for updates... (${pollCount}/36)` : 'Refresh SOW list'}
            >
              <RefreshCw size={18} className={isPolling ? 'spinning' : ''} />
              {isPolling ? `Checking (${pollCount})` : 'Refresh'}
            </button>
            <button className="create-sow-btn" onClick={handleCreateSOW}>
              <Plus size={20} />
              Create {selectedTab} SOW
            </button>
          </div>
        </div>

        {getFilteredSOWs().length > 0 ? (
          <div className="sows-list">
            {getFilteredSOWs().map((sow) => (
              <div key={sow.sow_id} className="sow-card">
                <button
                  className="delete-sow-btn"
                  onClick={(e) => handleDeleteSOWClick(sow, e)}
                  title="Delete SOW"
                >
                  <Trash2 size={16} />
                </button>
                <div className="sow-card-content">
                  <div className="sow-card-icon" style={{ backgroundColor: `${getModeColor(sow.mode)}20` }}>
                    <FileText size={24} color={getModeColor(sow.mode)} />
                  </div>
                  <div className="sow-card-body">
                    <h3>{getModeLabel(sow.mode)}</h3>
                    <p>{sow.project_name}</p>
                    <div className="sow-meta">
                      <span className="meta-item">
                        <Calendar size={14} />
                        {formatDate(sow.linked_at)}
                      </span>
                      <span className="meta-item">
                        <User size={14} />
                        {sow.customer_name}
                      </span>
                      <span className="meta-item">
                        Tokens: {formatTokenCount(sow.total_tokens)}
                      </span>
                    </div>
                  </div>
                  <div className="sow-card-actions">
                    <button
                      onClick={(e) => handleRegenerateSOW(sow, e)}
                      className="to-prod-btn"
                      title="Regenerate and refine"
                    >
                      <RefreshCw size={18} />
                      Regenerate
                    </button>
                    {(sow.s3_url || sow.drive_link) && (
                      <button
                        onClick={() => handleDownloadSOW(sow)}
                        className="download-btn"
                        title="Download SOW document"
                      >
                        <Download size={18} />
                        Download
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : isPolling ? (
          <div className="empty-state polling">
            <Loader className="spinning-loader" size={48} color="#2563eb" />
            <h3>Generating SOW...</h3>
            <p>Your document is being created. This usually takes 2-5 minutes.</p>
            <p className="poll-status">Checked {pollCount} time{pollCount !== 1 ? 's' : ''}</p>
            <button className="stop-polling-btn" onClick={stopPolling}>
              Stop Checking
            </button>
          </div>
        ) : (
          <div className="empty-state">
            <FileText size={64} color="#d1d5db" />
            <h3>No {getModeLabel(selectedTab)} SOWs Yet</h3>
            <p>Create your first {selectedTab} SOW for this project</p>
            <button className="create-first-btn" onClick={handleCreateSOW}>
              <Plus size={20} />
              Create First SOW
            </button>
          </div>
        )}
      </div>

      {/* Delete SOW Confirmation Modal */}
      {showDeleteSOWModal && sowToDelete && (
        <div className="modal-overlay" onClick={() => setShowDeleteSOWModal(false)}>
          <div className="modal-content delete-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Delete SOW</h2>
              <button className="modal-close" onClick={() => setShowDeleteSOWModal(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              <div className="warning-message">
                <AlertCircle size={48} color="#ef4444" />
                <p>Are you sure you want to delete this <strong>{getModeLabel(sowToDelete.mode)}</strong>?</p>
                <p className="warning-details">
                  This will permanently delete:
                </p>
                <ul className="warning-list">
                  <li>SOW document for {sowToDelete.project_name}</li>
                  <li>Created on {formatDate(sowToDelete.linked_at)}</li>
                  <li>Customer: {sowToDelete.customer_name}</li>
                </ul>
                <p className="warning-final">This action cannot be undone.</p>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" className="btn-secondary" onClick={() => setShowDeleteSOWModal(false)}>
                Cancel
              </button>
              <button type="button" className="btn-danger" onClick={handleDeleteSOWConfirm}>
                <Trash2 size={16} />
                <span>Delete SOW</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Drafts Modal */}
      {showDraftsModal && (
        <div className="modal-overlay" onClick={() => setShowDraftsModal(false)}>
          <div className="modal-content drafts-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>📝 In-Memory Preview Drafts</h2>
              <button className="modal-close" onClick={() => setShowDraftsModal(false)}>
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              {activePreviews.length === 0 ? (
                <div className="no-drafts">
                  <FileEdit size={64} color="#d1d5db" />
                  <p>No active preview drafts</p>
                  <p className="no-drafts-hint">Start creating a SOW to generate a preview draft</p>
                </div>
              ) : (
                <div className="drafts-list">
                  {activePreviews.map((draft) => (
                    <div key={draft.preview_id} className="draft-item">
                      <div className="draft-icon">
                        <FileEdit size={24} color={getModeColor(draft.mode)} />
                      </div>
                      <div className="draft-details">
                        <h3>{draft.metadata.project_title}</h3>
                        <p>{draft.metadata.company_name}</p>
                        <div className="draft-meta">
                          <span className="draft-mode" style={{ color: getModeColor(draft.mode) }}>
                            {getModeLabel(draft.mode)}
                          </span>
                          <span className="draft-status">
                            {draft.progress === 100 ? 'Ready' : (draft.current_step || 'Generating...')}
                          </span>
                        </div>
                        {draft.progress !== undefined && draft.progress !== 100 && (
                          <div className="draft-progress">
                            <div className="progress-bar-mini">
                              <div
                                className="progress-bar-fill-mini"
                                style={{ width: `${draft.progress}%` }}
                              ></div>
                            </div>
                            <span className="progress-text-mini">{draft.progress}%</span>
                          </div>
                        )}
                      </div>
                      <button
                        className="continue-draft-btn"
                        onClick={() => handleContinueDraft(draft)}
                        disabled={draft.progress !== 100}
                        title={draft.progress === 100 ? 'Continue editing this draft' : 'Wait for preview to complete'}
                      >
                        {draft.progress === 100 ? (
                          <>
                            <Edit size={16} />
                            Continue
                          </>
                        ) : (
                          <>
                            <Loader size={16} className="spinning" />
                            Generating...
                          </>
                        )}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <p className="draft-note">
                💡 <strong>Note:</strong> Preview drafts are stored in-memory only and will be lost when the server restarts.
                Finalize your SOW to save it permanently.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProjectDetail;
