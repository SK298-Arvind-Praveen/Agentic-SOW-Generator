import React, { useEffect, useRef, useState } from 'react';
import { FileText, Loader, Save, Search, Settings, Trash2, Upload, X } from 'lucide-react';
import apiService, { CustomSowTemplate } from '../services/apiService';
import './CustomTemplateSelector.css';

interface Props {
  value: CustomSowTemplate | null;
  onChange: (template: CustomSowTemplate | null) => void;
  disabled?: boolean;
}

const ALLOWED = new Set(['doc', 'docx', 'pdf']);

const CustomTemplateSelector: React.FC<Props> = ({ value, onChange, disabled }) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [presets, setPresets] = useState<CustomSowTemplate[]>([]);
  const [extracting, setExtracting] = useState(false);
  const [presetName, setPresetName] = useState('');
  const [error, setError] = useState('');
  const [manageOpen, setManageOpen] = useState(false);
  const [manageQuery, setManageQuery] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<CustomSowTemplate | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadPresets = async () => {
    try {
      const response = await apiService.fetchCustomTemplates();
      if (response.success) setPresets(response.templates || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load template presets');
    }
  };

  useEffect(() => { void loadPresets(); }, []);

  const extract = async (file?: File) => {
    if (!file) return;
    const extension = file.name.split('.').pop()?.toLowerCase() || '';
    if (!ALLOWED.has(extension)) {
      setError('Choose one DOC, DOCX, or PDF file.');
      return;
    }
    setError('');
    setExtracting(true);
    try {
      if (value && !value.saved) await apiService.deleteCustomTemplate(value.template_id);
      const response = await apiService.extractCustomTemplate(file);
      if (!response.extraction_id) throw new Error('Template extraction did not start');
      let template: CustomSowTemplate | undefined;
      for (let attempt = 0; attempt < 300; attempt += 1) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        const status = await apiService.fetchCustomTemplateExtraction(response.extraction_id);
        if (status.status === 'failed' || status.success === false) {
          throw new Error(status.error || 'Template extraction failed');
        }
        if (status.status === 'ready' && status.template) {
          template = status.template;
          break;
        }
      }
      if (!template) throw new Error('Template extraction timed out after 10 minutes');
      onChange(template);
      setPresetName('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to extract this template');
    } finally {
      setExtracting(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const clearToDefault = async () => {
    try {
      if (value && !value.saved) await apiService.deleteCustomTemplate(value.template_id);
    } catch {
      // The local selection should still be clearable if transient cleanup is unavailable.
    }
    onChange(null);
  };

  const choosePreset = async (templateId: string) => {
    const next = presets.find(item => item.template_id === templateId) || null;
    try {
      if (value && !value.saved && value.template_id !== next?.template_id) {
        await apiService.deleteCustomTemplate(value.template_id);
      }
    } catch {
      // Selection is still allowed; backend TTL/maintenance can reap the draft.
    }
    onChange(next);
  };

  const savePreset = async () => {
    if (!value || !presetName.trim()) return;
    try {
      const response = await apiService.saveCustomTemplate(value.template_id, presetName.trim());
      onChange(response.template);
      setPresetName('');
      await loadPresets();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save template preset');
    }
  };

  const removePreset = async (template: CustomSowTemplate) => {
    setDeleting(true);
    try {
      await apiService.deleteCustomTemplate(template.template_id);
      if (value?.template_id === template.template_id) onChange(null);
      await loadPresets();
      setDeleteTarget(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to delete template preset');
    } finally {
      setDeleting(false);
    }
  };

  const managedPresets = presets.filter(template => {
    const query = manageQuery.trim().toLowerCase();
    return !query || `${template.name} ${template.author} ${template.source_filename || ''}`.toLowerCase().includes(query);
  });

  return (
    <section className="custom-template-box" aria-labelledby="custom-template-title">
      <div className="custom-template-heading">
        <div>
          <div id="custom-template-title" className="field-label">Custom SOW template <span className="optional-label">(optional)</span></div>
          <p>Upload one existing SOW or select a shared preset.</p>
        </div>
        {value && <button type="button" className="template-clear" onClick={() => void clearToDefault()} disabled={disabled}><X size={15} /> Use default</button>}
      </div>

      <div className="custom-template-controls">
        <select
          value={value?.saved ? value.template_id : ''}
          onChange={event => void choosePreset(event.target.value)}
          disabled={disabled || extracting}
          aria-label="Saved custom template"
        >
          <option value="">Default template</option>
          {presets.map(template => (
            <option key={template.template_id} value={template.template_id}>{template.name} — {template.author}</option>
          ))}
        </select>
        <input
          ref={inputRef}
          type="file"
          accept=".doc,.docx,.pdf"
          hidden
          onChange={event => void extract(event.target.files?.[0])}
        />
        <button type="button" onClick={() => inputRef.current?.click()} disabled={disabled || extracting}>
          {extracting ? <Loader className="template-spinner" size={16} /> : <Upload size={16} />}
          {extracting ? 'Extracting template…' : 'Upload existing SOW'}
        </button>
        <button type="button" onClick={() => setManageOpen(true)} disabled={disabled}>
          <Settings size={16} /> Manage templates
        </button>
      </div>

      {value && (
        <div className="template-selected">
          <FileText size={18} />
          <div>
            <strong>{value.saved ? value.name : value.source_filename || 'Extracted template'}</strong>
            <span>{value.sections.length} reusable section{value.sections.length === 1 ? '' : 's'} · {value.author}</span>
          </div>
        </div>
      )}

      {value && !value.saved && (
        <div className="template-save-row">
          <input value={presetName} onChange={event => setPresetName(event.target.value)} maxLength={80} placeholder="Preset name" aria-label="Template preset name" />
          <button type="button" onClick={savePreset} disabled={!presetName.trim() || disabled}><Save size={15} /> Save for reuse</button>
        </div>
      )}

      {error && <p className="template-error">{error}</p>}
      {manageOpen && (
        <div className="template-manager-overlay" onMouseDown={() => !deleting && setManageOpen(false)}>
          <div className="template-manager-modal" role="dialog" aria-modal="true" aria-labelledby="template-manager-title" onMouseDown={event => event.stopPropagation()}>
            <div className="template-manager-header">
              <div><h2 id="template-manager-title">Manage templates</h2><p>{presets.length} shared preset{presets.length === 1 ? '' : 's'}</p></div>
              <button type="button" className="template-manager-close" onClick={() => setManageOpen(false)} disabled={deleting}><X size={20} /></button>
            </div>
            <div className="template-manager-search"><Search size={16} /><input value={manageQuery} onChange={event => setManageQuery(event.target.value)} placeholder="Search templates, authors or source files" /></div>
            <div className="template-manager-list">
              {managedPresets.length ? managedPresets.map(template => (
                <div className="template-manager-row" key={template.template_id}>
                  <FileText size={19} />
                  <div className="template-manager-details">
                    <strong>{template.name}</strong>
                    <span>By {template.author} · {template.sections.length} reusable section{template.sections.length === 1 ? '' : 's'}</span>
                    <small>{template.source_filename || 'Saved custom template'}</small>
                  </div>
                  {template.can_delete ? <button type="button" className="template-manager-delete" onClick={() => setDeleteTarget(template)} disabled={deleting}><Trash2 size={16} /> Delete</button> : <span className="template-manager-shared">Shared</span>}
                </div>
              )) : <div className="template-manager-empty">No templates match this search.</div>}
            </div>
            {deleteTarget && <div className="template-delete-confirmation">
              <div><strong>Delete “{deleteTarget.name}”?</strong><span>This removes the preset for everyone and cannot be undone.</span></div>
              <button type="button" onClick={() => setDeleteTarget(null)} disabled={deleting}>Cancel</button>
              <button type="button" className="confirm" onClick={() => void removePreset(deleteTarget)} disabled={deleting}>{deleting ? 'Deleting…' : 'Delete preset'}</button>
            </div>}
          </div>
        </div>
      )}
    </section>
  );
};

export default CustomTemplateSelector;
