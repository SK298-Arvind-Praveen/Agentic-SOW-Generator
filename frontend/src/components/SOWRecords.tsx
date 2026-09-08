import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { Download, FilePlus, Files, RefreshCw, Search, Upload, X } from 'lucide-react';
import apiService, { Document, SourceDocument } from '../services/apiService';
import { downloadWithNativeSaveAs } from '../utils/downloadFile';
import { formatTokenCount } from '../utils/tokenUsage';
import './Dashboard.css';
import './SOWRecords.css';

type HistoryRecord = Document & {
  document?: Document;
  task?: { metadata?: Document };
};

const documentData = (record: HistoryRecord): Document => record.document || record;
const taskMetadata = (record: HistoryRecord): Document => record.task?.metadata || {};

const recordDate = (record: Document): string => (
  record.timestamp || record.created_at || record.document_date || record.date || ''
);

const displayDate = (record: Document): string => {
  const value = recordDate(record);
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
};

const generatedAt = (record: HistoryRecord): number => {
  const parsed = new Date(recordDate(documentData(record))).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
};

const sowName = (record: HistoryRecord): string => {
  const document = documentData(record);
  const metadata = taskMetadata(record);
  const project = document.project_name || document.name || document.title || metadata.project_name || 'Untitled SOW';
  const suffix = [document.mode || record.task?.metadata?.mode, document.version].filter(Boolean).join(' ');
  return suffix ? `${project} - ${suffix}` : project;
};

const SOWRecords: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const handledRegenerationLink = useRef(false);
  const [records, setRecords] = useState<HistoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [refinementRecord, setRefinementRecord] = useState<HistoryRecord | null>(null);
  const [refinementInstructions, setRefinementInstructions] = useState('');
  const [refinementFiles, setRefinementFiles] = useState<File[]>([]);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [sourceRecord, setSourceRecord] = useState<HistoryRecord | null>(null);
  const [sourceDocuments, setSourceDocuments] = useState<SourceDocument[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);

  useEffect(() => {
    let active = true;
    apiService.fetchDocuments({ mine: true, limit: 1000 }).then(response => {
      if (!active) return;
      if (!response.success) toast.error('Unable to load your SOW records');
      setRecords([...(response.documents || [])].sort((a, b) => generatedAt(b) - generatedAt(a)));
      setLoading(false);
    });
    return () => { active = false; };
  }, []);

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

  const filteredRecords = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return records;
    return records.filter(record => {
      const document = documentData(record);
      const metadata = taskMetadata(record);
      return (
      `${sowName(record)} ${document.business_unit || metadata.business_unit || ''} ${document.owner_name || metadata.owner_name || document.author_name || document.author || ''}`
        .toLowerCase()
        .includes(query)
      );
    });
  }, [records, searchQuery]);

  const download = async (record: HistoryRecord) => {
    const document = documentData(record);
    const url = document.s3_url || document.drive_link || '';
    if (!url) {
      toast.error('This SOW does not have a downloadable document');
      return;
    }
    const filename = `${sowName(record).replace(/[<>:"/\\|?*]/g, '_')}.docx`;
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
        <div className="records-search-container">
          <Search className="records-search-icon" size={14} />
          <input
            type="text"
            placeholder="Search your SOW records..."
            className="records-search-input"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
          />
        </div>
      </div>

      <div className="records-table-container">
        <table className="records-table">
          <thead><tr>
            <th>SOW Name</th>
            <th>Business Unit</th>
            <th>Created By</th>
            <th>Created Date</th>
            <th>Total Tokens</th>
            <th style={{ textAlign: 'center' }}>Actions</th>
          </tr></thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="no-records">Loading your SOW records…</td></tr>
            ) : filteredRecords.length === 0 ? (
              <tr><td colSpan={6} className="no-records">
                <div className="sow-empty-state">
                  <FilePlus size={32} />
                  <p className="sow-empty-title">No SOWs found</p>
                  <p className="sow-empty-subtitle">
                    {records.length ? 'No records match your search.' : "You haven't generated any SOWs yet."}
                  </p>
                  {!records.length && <button type="button" className="sow-empty-cta" onClick={() => navigate('/dashboard')}>Create SOW</button>}
                </div>
              </td></tr>
            ) : filteredRecords.map(record => {
              const document = documentData(record);
              const metadata = taskMetadata(record);
              return (
              <tr key={`${document.document_id || document.id}-${document.timestamp || document.version}`}>
                <td><div className="sow-name-cell">{sowName(record)}</div></td>
                <td>{document.business_unit || metadata.business_unit || 'Unassigned'}</td>
                <td>{document.owner_name || metadata.owner_name || document.author_name || document.author || metadata.author_name || 'Unknown'}</td>
                <td>{displayDate(document)}</td>
                <td>{formatTokenCount(document.total_tokens ?? metadata.total_tokens)}</td>
                <td><div className="action-buttons">
                  <button className="download-icon-btn" title="Download SOW" onClick={() => download(record)}>
                    <Download size={16} />
                  </button>
                  <button className="download-icon-btn" title="Regenerate and refine" onClick={() => openRegeneration(record)}>
                    <RefreshCw size={16} />
                  </button>
                  <button className="download-icon-btn" title="View uploaded documents" onClick={() => openSources(record)}>
                    <Files size={16} />
                  </button>
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
    </div>
  );
};

export default SOWRecords;
