import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { toast } from '../utils/toast';
import { Download, Eye, FilePlus, Files, RefreshCw, Search, Trash2, Upload, X } from 'lucide-react';
import apiService, { Document, SourceDocument } from '../services/apiService';
import { downloadWithNativeSaveAs } from '../utils/downloadFile';
import { formatTokenCount } from '../utils/tokenUsage';
import { documentTimestamp, formatDocumentDateTime, sowDownloadFilename } from '../utils/documentPresentation';
import './Dashboard.css';
import './SOWRecords.css';
import { useAuth } from '../contexts/AuthContext';
import SOWDeleteDialog from './SOWDeleteDialog';

type HistoryRecord = Document & {
  is_processing?: boolean;
  document?: Document;
  task?: { metadata?: Document };
};

const documentData = (record: HistoryRecord): Document => record.document || record;
const taskMetadata = (record: HistoryRecord): Document => record.task?.metadata || {};

const recordDate = (record: Document): string => (
  documentTimestamp(record)
);

const displayDate = (record: Document): string => {
  return formatDocumentDateTime(recordDate(record));
};

const generatedAt = (record: HistoryRecord): number => {
  const parsed = new Date(recordDate(documentData(record))).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
};

const versionNumber = (value?: string): number => Number(value?.match(/\d+/)?.[0] || 0);

const latestVersions = (items: HistoryRecord[]): HistoryRecord[] => {
  const latest = new Map<string, HistoryRecord>();
  items.forEach(record => {
    const document = documentData(record);
    const metadata = taskMetadata(record);
    const owner = String(document.owner_email || metadata.owner_email || '').trim().toLowerCase();
    const mode = String(document.mode || metadata.mode || '').trim().toLowerCase();
    const projectId = String(document.project_id || metadata.project_id || '').trim().toLowerCase();
    const scopeId = String(document.source_scope_id || metadata.source_scope_id || '').trim().toLowerCase();
    const project = String(document.project_name || document.name || document.title || metadata.project_name || '').trim().toLowerCase();
    const customer = String(document.customer_name || document.company_name || metadata.customer_name || metadata.company_name || '').trim().toLowerCase();
    const id = String(document.document_id || document.id || document.doc_id || '');
    const lineage = projectId ? `project:${owner}:${projectId}:${mode}`
      : scopeId ? `scope:${owner}:${scopeId}:${mode}`
        : project ? `names:${owner}:${customer}:${project}:${mode}` : `document:${id}`;
    const current = latest.get(lineage);
    const currentDocument = current ? documentData(current) : undefined;
    if (!current || versionNumber(document.version) > versionNumber(currentDocument?.version)
      || (versionNumber(document.version) === versionNumber(currentDocument?.version) && generatedAt(record) > generatedAt(current))) {
      latest.set(lineage, record);
    }
  });
  return Array.from(latest.values()).sort((a, b) => generatedAt(b) - generatedAt(a));
};

const sowName = (record: HistoryRecord): string => {
  const document = documentData(record);
  const metadata = taskMetadata(record);
  const project = document.project_name || document.name || document.title || metadata.project_name || 'Untitled SOW';
  const suffix = [document.mode || record.task?.metadata?.mode, document.version].filter(Boolean).join(' ');
  return suffix ? `${project} - ${suffix}` : project;
};

const isDraft = (record: HistoryRecord): boolean => (
  String(documentData(record).status || taskMetadata(record).status || '').toLowerCase() === 'draft'
);

const SOWRecords: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { isAdmin } = useAuth();
  const handledRegenerationLink = useRef(false);
  const [records, setRecords] = useState<HistoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [semanticSearch, setSemanticSearch] = useState(false);
  const [semanticResults, setSemanticResults] = useState<HistoryRecord[]>([]);
  const [semanticLoading, setSemanticLoading] = useState(false);
  const [semanticIndexing, setSemanticIndexing] = useState(false);
  const semanticRequest = useRef(0);
  const [refinementRecord, setRefinementRecord] = useState<HistoryRecord | null>(null);
  const [refinementInstructions, setRefinementInstructions] = useState('');
  const [refinementFiles, setRefinementFiles] = useState<File[]>([]);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [sourceRecord, setSourceRecord] = useState<HistoryRecord | null>(null);
  const [sourceDocuments, setSourceDocuments] = useState<SourceDocument[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<HistoryRecord | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let active = true;
    apiService.fetchDocuments({ mine: !isAdmin, limit: 1000 }).then(response => {
      if (!active) return;
      if (!response.success) toast.error('Unable to load your SOW records');
      setRecords([...(response.documents || [])].filter(record => !(record as HistoryRecord).is_processing).sort((a, b) => generatedAt(b) - generatedAt(a)));
      setLoading(false);
    });
    return () => { active = false; };
  }, [isAdmin]);

  useEffect(() => {
    if (handledRegenerationLink.current || loading || !records.length) return;
    const requestedId = new URLSearchParams(location.search).get('regenerate');
    if (!requestedId) return;
    const match = records.find(record => recordId(record) === requestedId);
    handledRegenerationLink.current = true;
    if (match) openRegeneration(match);
    else toast.error('The requested SOW record is not available');
  // recordId/openRegeneration are stable helpers over current state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, records, location.search]);

  useEffect(() => {
    const query = searchQuery.trim();
    if (!semanticSearch || !query) {
      semanticRequest.current += 1;
      setSemanticLoading(false);
      setSemanticIndexing(false);
      setSemanticResults([]);
      return;
    }
    const requestId = ++semanticRequest.current;
    const timer = window.setTimeout(async () => {
      setSemanticLoading(true);
      setSemanticIndexing(false);
      try {
        for (let attempt = 0; attempt < 8; attempt += 1) {
          const response = await apiService.semanticSearchDocuments(query, { mine: !isAdmin, limit: 1000 });
          if (requestId !== semanticRequest.current) return;
          if (!response.success) throw new Error((response as any).error || 'Semantic search failed');
          if (!response.indexing) {
            setSemanticIndexing(false);
            setSemanticResults((response.documents || []) as HistoryRecord[]);
            return;
          }
          setSemanticIndexing(true);
          await new Promise(resolve => window.setTimeout(resolve, 850));
        }
        throw new Error('Existing SOWs are still being indexed. Try again in a moment.');
      } catch (error) {
        if (requestId !== semanticRequest.current) return;
        setSemanticResults([]);
        toast.error(error instanceof Error ? error.message : 'Semantic search is unavailable');
      } finally {
        if (requestId === semanticRequest.current) setSemanticLoading(false);
      }
    }, 650);
    return () => window.clearTimeout(timer);
  }, [searchQuery, semanticSearch, isAdmin]);

  const filteredRecords = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (semanticSearch) return query ? semanticResults : latestVersions(records);
    if (!query) return records;
    return records.filter(record => {
      const document = documentData(record);
      const metadata = taskMetadata(record);
      return (
      `${sowName(record)} ${document.owner_name || metadata.owner_name || document.author_name || document.author || ''}`
        .toLowerCase()
        .includes(query)
      );
    });
  }, [records, searchQuery, semanticSearch, semanticResults]);

  const download = async (record: HistoryRecord) => {
    const document = documentData(record);
    const url = document.s3_url || document.drive_link || '';
    if (!url) {
      toast.error('This SOW does not have a downloadable document');
      return;
    }
    const metadata = taskMetadata(record);
    const filename = sowDownloadFilename({
      ...document,
      project_name: document.project_name || document.name || document.title || metadata.project_name,
      mode: document.mode || metadata.mode,
      version: document.version || metadata.version,
    });
    try {
      await downloadWithNativeSaveAs(
        () => apiService.downloadDocument(url, document.document_id),
        filename,
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Download failed');
    }
  };

  const recordId = (record: HistoryRecord): string => {
    const document = documentData(record);
    return String(document.document_id || document.id || document.doc_id || '');
  };

  const deleteSOW = async () => {
    if (!deleteTarget || deleting) return;
    const id = recordId(deleteTarget);
    setDeleting(true);
    try {
      const response = isDraft(deleteTarget)
        ? await apiService.deleteDraftSOW(id)
        : await apiService.deleteSOW(id);
      if (!response.success) throw new Error(response.error || 'Unable to delete SOW');
      setRecords(current => current.filter(record => recordId(record) !== id));
      setSemanticResults(current => current.filter(record => recordId(record) !== id));
      setDeleteTarget(null);
      toast.success(isDraft(deleteTarget) ? 'Draft permanently deleted' : 'SOW permanently deleted');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Unable to delete SOW');
    } finally {
      setDeleting(false);
    }
  };

  const openDraft = async (record: HistoryRecord) => {
    const id = recordId(record);
    if (!id) return toast.error('This draft has no document identifier');
    const toastId = toast.loading('Opening draft…', { autoClose: false });
    try {
      const response = await apiService.openDraftSOW(id);
      if (!response.success || !response.preview_id) throw new Error(response.error || 'Unable to open draft');
      localStorage.setItem('lastPreviewId', response.preview_id);
      localStorage.setItem('loadingFromDraft', 'true');
      toast.update(toastId, { render: 'Draft opened', type: 'success', isLoading: false, autoClose: 1500 });
      navigate('/dashboard', { state: { view: 'generate' } });
    } catch (error) {
      toast.update(toastId, { render: error instanceof Error ? error.message : 'Unable to open draft', type: 'error', isLoading: false, autoClose: 5000 });
    }
  };

  const openRegeneration = (record: HistoryRecord) => {
    setRefinementRecord(record);
    setRefinementInstructions('');
    setRefinementFiles([]);
  };

  const submitRegeneration = async () => {
    if (!refinementRecord) return;
    const documentId = recordId(refinementRecord);
    if (!documentId) {
      toast.error('This record has no document identifier');
      return;
    }
    if (!refinementInstructions.trim() && refinementFiles.length === 0) {
      toast.error('Enter modification instructions or upload a revised document');
      return;
    }
    setIsRegenerating(true);
    const toastId = toast.loading('Starting SOW refinement…');
    try {
      const response = await apiService.regenerateSOW(
        documentId,
        refinementInstructions.trim(),
        refinementFiles,
      );
      if (!response.success || !response.preview_id) {
        throw new Error(response.error || 'Unable to start SOW refinement');
      }
      localStorage.setItem('lastPreviewId', response.preview_id);
      localStorage.setItem('loadingFromDraft', 'true');
      toast.update(toastId, {
        render: 'Refinement started. Opening the preview workspace…',
        type: 'success', isLoading: false, autoClose: 2500,
      });
      setRefinementRecord(null);
      navigate('/dashboard', { state: { view: 'generate' } });
    } catch (error) {
      toast.update(toastId, {
        render: error instanceof Error ? error.message : 'Unable to regenerate SOW',
        type: 'error', isLoading: false, autoClose: 5000,
      });
    } finally {
      setIsRegenerating(false);
    }
  };

  const openSources = async (record: HistoryRecord) => {
    const documentId = recordId(record);
    if (!documentId) return toast.error('This record has no document identifier');
    setSourceRecord(record);
    setSourceDocuments([]);
    setSourcesLoading(true);
    const response = await apiService.fetchSourceDocuments(documentId);
    setSourcesLoading(false);
    if (!response.success) toast.error(response.error || 'Unable to load supporting documents');
    setSourceDocuments(response.documents || []);
  };

  const downloadSource = async (source: SourceDocument) => {
    if (!sourceRecord) return;
    try {
      await downloadWithNativeSaveAs(
        () => apiService.downloadSourceDocument(recordId(sourceRecord), source.source_id),
        source.filename,
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Supporting-document download failed');
    }
  };

  return (
    <div className="records-view sow-records-page">
      <div className="records-header">
        <div className="records-header-left">
          <h1>SOW Records</h1>
          <p>All SOW documents generated by your account</p>
        </div>
        <div className="sow-search-controls">
          <div className="records-search-container">
            <Search className="records-search-icon" size={14} />
            <input
              type="text"
              placeholder={semanticSearch ? 'Search by meaning or intent...' : 'Search your SOW records...'}
              className="records-search-input"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </div>
          <label className="semantic-search-toggle">
            <input
              type="checkbox"
              checked={semanticSearch}
              onChange={event => setSemanticSearch(event.target.checked)}
            />
            <span>Semantic search</span>
          </label>
        </div>
      </div>

      <div className="records-table-container">
        <table className="records-table">
          <thead><tr>
            <th>SOW Name</th>
            <th>Created By</th>
            <th>Created Date</th>
            <th>Total Tokens</th>
            {semanticSearch && <th>Closeness</th>}
            <th style={{ textAlign: 'center' }}>Actions</th>
          </tr></thead>
          <tbody>
            {loading || semanticLoading ? (
              <tr><td colSpan={semanticSearch ? 6 : 5} className="no-records">{semanticLoading ? (semanticIndexing ? 'Preparing semantic search index…' : 'Finding semantically similar SOWs…') : 'Loading your SOW records…'}</td></tr>
            ) : filteredRecords.length === 0 ? (
              <tr><td colSpan={semanticSearch ? 6 : 5} className="no-records">
                <div className="sow-empty-state">
                  <FilePlus size={32} />
                  <p className="sow-empty-title">No SOWs found</p>
                  {(!semanticSearch || !records.length) && (
                    <p className="sow-empty-subtitle">
                      {records.length ? 'No records match your search.' : "You haven't generated any SOWs yet."}
                    </p>
                  )}
                  {!records.length && <button type="button" className="sow-empty-cta" onClick={() => navigate('/dashboard')}>Create SOW</button>}
                </div>
              </td></tr>
            ) : filteredRecords.map(record => {
              const document = documentData(record);
              const metadata = taskMetadata(record);
              return (
              <tr key={`${document.document_id || document.id}-${document.timestamp || document.version}`}>
                <td><div className="sow-name-cell">{sowName(record)}{isDraft(record) && <> - <em className="sow-draft-label">Draft</em></>}</div></td>
                <td>{document.owner_name || metadata.owner_name || document.author_name || document.author || metadata.author_name || 'Unknown'}</td>
                <td>{displayDate(document)}</td>
                <td>{formatTokenCount(document.total_tokens ?? metadata.total_tokens)}</td>
                {semanticSearch && <td><span className="semantic-score">{typeof document.similarity_score === 'number' ? `${document.similarity_score.toFixed(2)}%` : '—'}</span></td>}
                <td><div className="action-buttons">
                  {isDraft(record) ? <>
                    <button className="download-icon-btn" title="View draft" aria-label="View draft" onClick={() => void openDraft(record)}><Eye size={16} /></button>
                    <button className="download-icon-btn sow-delete-icon" title="Delete draft" aria-label="Delete draft" onClick={() => setDeleteTarget(record)}><Trash2 size={16} /></button>
                  </> : <>
                    <button className="download-icon-btn" title="Download SOW" onClick={() => download(record)}><Download size={16} /></button>
                    <button className="download-icon-btn" title="Regenerate and refine" onClick={() => openRegeneration(record)}><RefreshCw size={16} /></button>
                    <button className="download-icon-btn" title="View uploaded documents" onClick={() => openSources(record)}><Files size={16} /></button>
                    {isAdmin && <button className="download-icon-btn sow-delete-icon" title="Permanently delete SOW" onClick={() => setDeleteTarget(record)}><Trash2 size={16} /></button>}
                  </>}
                </div></td>
              </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {refinementRecord && (
        <div className="modal-overlay" onClick={() => !isRegenerating && setRefinementRecord(null)}>
          <div className="modal-content sow-refinement-modal" onClick={event => event.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h2>Regenerate SOW</h2>
                <p>{sowName(refinementRecord)}</p>
              </div>
              <button className="modal-close" disabled={isRegenerating} onClick={() => setRefinementRecord(null)}><X size={20} /></button>
            </div>
            <div className="modal-body sow-refinement-body">
              <label htmlFor="refinement-instructions">Modification instructions</label>
              <textarea
                id="refinement-instructions"
                value={refinementInstructions}
                onChange={event => setRefinementInstructions(event.target.value)}
                placeholder="Describe what should change and what must remain unchanged…"
                rows={7}
              />
              <label className="sow-refinement-upload">
                <Upload size={18} />
                <span>Upload new or revised supporting documents</span>
                <input
                  type="file"
                  multiple
                  accept=".pdf,.doc,.docx,.xls,.xlsx,.txt"
                  onChange={event => setRefinementFiles(Array.from(event.target.files || []))}
                />
              </label>
              <p className="sow-refinement-help">Supported: PDF, Word, Excel, and TXT. Unchanged files are reused; small revisions send only their text diff to the refinement agent.</p>
              {refinementFiles.length > 0 && (
                <ul className="sow-refinement-file-list">
                  {refinementFiles.map(file => <li key={`${file.name}-${file.size}`}>{file.name}</li>)}
                </ul>
              )}
            </div>
            <div className="modal-footer">
              <button className="modal-btn modal-btn-secondary" disabled={isRegenerating} onClick={() => setRefinementRecord(null)}>Cancel</button>
              <button className="modal-btn modal-btn-primary" disabled={isRegenerating} onClick={submitRegeneration}>
                {isRegenerating ? 'Starting…' : 'Generate refined preview'}
              </button>
            </div>
          </div>
        </div>
      )}

      {sourceRecord && (
        <div className="modal-overlay" onClick={() => setSourceRecord(null)}>
          <div className="modal-content sow-sources-modal" onClick={event => event.stopPropagation()}>
            <div className="modal-header">
              <div><h2>Uploaded documents</h2><p>{sowName(sourceRecord)}</p></div>
              <button className="modal-close" onClick={() => setSourceRecord(null)}><X size={20} /></button>
            </div>
            <div className="modal-body">
              {sourcesLoading ? <p>Loading documents…</p> : sourceDocuments.length === 0 ? (
                <p className="sow-source-empty">No archived supporting documents are available for this project yet. They will appear here after a new upload or regeneration.</p>
              ) : (
                <div className="sow-source-list">
                  {sourceDocuments.map(source => (
                    <div className="sow-source-row" key={`${source.source_id}-${source.revision}`}>
                      <div><strong>{source.filename}</strong><span>Revision {source.revision} · {new Date(source.uploaded_at).toLocaleString()}</span></div>
                      <button className="download-icon-btn" title="Download supporting document" onClick={() => downloadSource(source)}><Download size={16} /></button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {deleteTarget && <SOWDeleteDialog
        name={sowName(deleteTarget)}
        deleting={deleting}
        onCancel={() => !deleting && setDeleteTarget(null)}
        onConfirm={() => void deleteSOW()}
      />}
    </div>
  );
};

export default SOWRecords;
