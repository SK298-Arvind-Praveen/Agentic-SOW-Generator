import React, { useEffect, useState } from 'react';
import { GripVertical, Plus, Settings, Trash2 } from 'lucide-react';
import './SOWSectionChecklist.css';
import apiService from '../services/apiService';
import { useAuth } from '../contexts/AuthContext';

export type GeneratorMode = 'poc' | 'production' | 'poc-to-production';

type SectionOption = {
  id: string;
  label: string;
  modes: GeneratorMode[];
  prompt?: string;
  custom?: boolean;
};

const ALL_MODES: GeneratorMode[] = ['poc', 'production', 'poc-to-production'];

export const SOW_SECTION_OPTIONS: SectionOption[] = [
  { id: 'document_version_control', label: 'Document Version Control', modes: ALL_MODES },
  { id: 'about_shellkode', label: 'About Shellkode', modes: ALL_MODES },
  { id: 'about_client', label: 'About Client', modes: ALL_MODES },
  { id: 'project_overview', label: 'Objective', modes: ALL_MODES },
  { id: 'scope_of_work', label: 'Scope of Work', modes: ALL_MODES },
  { id: 'architecture_diagram', label: 'Architecture Diagram', modes: ALL_MODES },
  { id: 'customer_dependencies', label: 'Customer Dependencies', modes: ALL_MODES },
  { id: 'assumptions', label: 'Assumptions', modes: ALL_MODES },
  { id: 'out_of_scope', label: 'Out of Scope', modes: ALL_MODES },
  { id: 'timelines_deliverables', label: 'Timelines and Deliverables', modes: ALL_MODES },
  { id: 'aws_pricing', label: 'AWS Pricing', modes: ALL_MODES },
  { id: 'customer_responsibilities', label: 'Customer Responsibilities', modes: ALL_MODES },
  { id: 'project_team_effort', label: 'Project Team Effort', modes: ALL_MODES },
  { id: 'open_clarifications', label: 'Open Clarifications', modes: ALL_MODES },
  { id: 'success_criteria', label: 'Success Criteria', modes: ALL_MODES },
  { id: 'project_plan_termination', label: 'Project Plan Termination', modes: ALL_MODES },
  { id: 'contacts_reporting', label: 'Contacts and Reporting', modes: ALL_MODES },
  { id: 'terms_conditions', label: 'Terms and Conditions', modes: ALL_MODES },
  { id: 'acceptance_signatories', label: 'Acceptance and Signatories', modes: ALL_MODES },
];

export const availableSowSectionIds = (mode: GeneratorMode): string[] =>
  SOW_SECTION_OPTIONS.filter(option => option.modes.includes(mode)).map(option => option.id);

interface SOWSectionChecklistProps {
  mode: GeneratorMode;
  selected: string[];
  onChange: (sectionIds: string[]) => void;
}

// A drag can originate either from the master (available) list — which adds the
// item to the order — or from within the order list itself — which reorders it.
type DragPayload = { source: 'available' | 'order'; id: string };

const SOWSectionChecklist: React.FC<SOWSectionChecklistProps> = ({ mode, selected, onChange }) => {
  const { isAdmin } = useAuth();
  const [options, setOptions] = useState<SectionOption[]>(SOW_SECTION_OPTIONS);
  const [showManager, setShowManager] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [sectionLabel, setSectionLabel] = useState('');
  const [sectionPrompt, setSectionPrompt] = useState('');
  const [catalogueError, setCatalogueError] = useState('');

  const loadSections = async () => {
    try {
      const response = await apiService.fetchSowSections();
      if (response.success && Array.isArray(response.sections)) setOptions(response.sections);
    } catch (error) {
      console.warn('Using bundled SOW section catalogue:', error);
    }
  };

  useEffect(() => { void loadSections(); }, []);

  const availableOptions = options.filter(option => option.modes.includes(mode));
  const availableIds = availableOptions.map(option => option.id);
  const selectedSet = new Set(selected);

  // The user's exact selected order — selected items filtered to what's valid for
  // this mode, in the order the user arranged them (never re-sorted to master order).
  const orderedSelected = selected.filter(id => availableIds.includes(id));

  // Left panel only shows sections that haven't been added to the SOW order yet —
  // once moved to the right, an item leaves this list entirely.
  const unselectedOptions = availableOptions.filter(option => !selectedSet.has(option.id));

  const [dragPayload, setDragPayload] = useState<DragPayload | null>(null);
  const [dropIndicatorIndex, setDropIndicatorIndex] = useState<number | null>(null);
  const labelFor = (id: string): string => options.find(option => option.id === id)?.label || id;

  const resetEditor = () => {
    setEditingId(null);
    setSectionLabel('');
    setSectionPrompt('');
    setCatalogueError('');
  };

  const saveCatalogueSection = async () => {
    if (!sectionLabel.trim()) return setCatalogueError('Section name is required.');
    try {
      if (editingId) {
        await apiService.updateSowSection(editingId, { label: sectionLabel, prompt: sectionPrompt });
      } else {
        await apiService.createSowSection({ label: sectionLabel, prompt: sectionPrompt });
      }
      resetEditor();
      await loadSections();
    } catch (error) {
      setCatalogueError(error instanceof Error ? error.message : 'Unable to save section');
    }
  };

  const editCatalogueSection = (option: SectionOption) => {
    setEditingId(option.id);
    setSectionLabel(option.label);
    setSectionPrompt(option.prompt || '');
    setCatalogueError('');
  };

  const deleteCatalogueSection = async (option: SectionOption) => {
    if (!window.confirm(`Delete “${option.label}” from the SOW section catalogue?`)) return;
    try {
      await apiService.deleteSowSection(option.id);
      onChange(orderedSelected.filter(id => id !== option.id));
      await loadSections();
    } catch (error) {
      setCatalogueError(error instanceof Error ? error.message : 'Unable to delete section');
    }
  };

  const addToOrder = (sectionId: string) => {
    if (selectedSet.has(sectionId)) return;
    onChange([...orderedSelected, sectionId]);
  };

  const clearSelected = () => onChange([]);

  const removeFromOrder = (sectionId: string) => {
    onChange(orderedSelected.filter(id => id !== sectionId));
  };

  const insertAt = (sectionId: string, index: number) => {
    const withoutItem = orderedSelected.filter(id => id !== sectionId);
    const clampedIndex = Math.max(0, Math.min(index, withoutItem.length));
    const next = [...withoutItem];
    next.splice(clampedIndex, 0, sectionId);
    onChange(next);
  };

  // ── Drag handlers: master (available) list rows ──
  const handleAvailableDragStart = (id: string) => (e: React.DragEvent<HTMLElement>) => {
    setDragPayload({ source: 'available', id });
    e.dataTransfer.effectAllowed = 'copyMove';
  };

  // Dropping an order-list item back onto the available panel removes it from the SOW.
  const handleAvailablePanelDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    if (dragPayload?.source === 'order') e.preventDefault();
  };
  const handleAvailablePanelDrop = (e: React.DragEvent<HTMLDivElement>) => {
    if (dragPayload?.source === 'order') {
      e.preventDefault();
      removeFromOrder(dragPayload.id);
    }
    setDragPayload(null);
    setDropIndicatorIndex(null);
  };

  // ── Drag handlers: order list rows ──
  const handleOrderItemDragStart = (id: string) => (e: React.DragEvent<HTMLDivElement>) => {
    setDragPayload({ source: 'order', id });
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleOrderItemDragOver = (index: number) => (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDropIndicatorIndex(index);
  };

  const handleOrderPanelDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (dropIndicatorIndex === null) setDropIndicatorIndex(orderedSelected.length);
  };

  const handleOrderPanelDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (dragPayload) {
      const targetIndex = dropIndicatorIndex ?? orderedSelected.length;
      insertAt(dragPayload.id, targetIndex);
    }
    setDragPayload(null);
    setDropIndicatorIndex(null);
  };

  const handleDragEnd = () => {
    setDragPayload(null);
    setDropIndicatorIndex(null);
  };

  return (
    <div className="sow-section-checklist" aria-labelledby="sow-section-checklist-title">
      <div className="checklist-heading-row">
        <div>
          <div id="sow-section-checklist-title" className="field-label">Customise SOW sections</div>
          <p className="checklist-help">Click or drag a section from Available into Selected to include it in your SOW, and feel free to rearrange it as needed.</p>
        </div>
        <div className="checklist-actions" aria-label="Section selection actions">
          <span className="checklist-count">{orderedSelected.length} selected</span>
          {isAdmin && (
            <button type="button" onClick={() => setShowManager(value => !value)}>
              <Settings size={14} /> Manage sections
            </button>
          )}
          <button type="button" onClick={clearSelected} disabled={orderedSelected.length === 0}>Clear selected</button>
        </div>
      </div>

      {isAdmin && showManager && (
        <div className="section-catalogue-manager">
          <div className="catalogue-editor">
            <input
              value={sectionLabel}
              onChange={event => setSectionLabel(event.target.value)}
              placeholder="Section name"
              aria-label="Section name"
            />
            <input
              value={sectionPrompt}
              onChange={event => setSectionPrompt(event.target.value)}
              placeholder="Generation instruction (optional)"
              aria-label="Section generation instruction"
            />
            <button type="button" onClick={saveCatalogueSection}>
              <Plus size={14} /> {editingId ? 'Save changes' : 'Add section'}
            </button>
            {editingId && <button type="button" onClick={resetEditor}>Cancel</button>}
          </div>
          {catalogueError && <p className="catalogue-error">{catalogueError}</p>}
          <div className="catalogue-items">
            {options.map(option => (
              <div className="catalogue-item" key={option.id}>
                <button type="button" className="catalogue-item-name" onClick={() => editCatalogueSection(option)}>
                  {option.label}
                </button>
                <button type="button" className="catalogue-delete" onClick={() => deleteCatalogueSection(option)} aria-label={`Delete ${option.label}`}>
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="checklist-two-panel">
        <div className="checklist-panel">
          <div className="checklist-panel-title">Available SOW sections</div>
          <div
            className="checklist-panel-body checklist-list"
            onDragOver={handleAvailablePanelDragOver}
            onDrop={handleAvailablePanelDrop}
          >
            {unselectedOptions.length === 0 ? (
              <p className="order-empty-message">All sections have been added to Selected.</p>
            ) : (
              unselectedOptions.map(option => (
                <button
                  type="button"
                  className="checklist-option"
                  key={option.id}
                  draggable
                  onClick={() => addToOrder(option.id)}
                  onDragStart={handleAvailableDragStart(option.id)}
                  onDragEnd={handleDragEnd}
                >
                  <span className="checklist-option-title">{option.label}</span>
                  <span className="drag-handle" aria-hidden="true"><GripVertical size={14} /></span>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="checklist-panel">
          <div className="checklist-panel-title">Selected SOW sections</div>
          <div
            className={`checklist-panel-body order-list ${dragPayload ? 'drop-active' : ''}`}
            onDragOver={handleOrderPanelDragOver}
            onDrop={handleOrderPanelDrop}
          >
            {orderedSelected.length === 0 ? (
              <p className="order-empty-message">Drag sections here to define the SOW order.</p>
            ) : (
              orderedSelected.map((id, index) => (
                <React.Fragment key={id}>
                  {dropIndicatorIndex === index && dragPayload && <div className="drop-indicator" />}
                  <div
                    className={`order-item ${dragPayload?.source === 'order' && dragPayload.id === id ? 'dragging' : ''}`}
                    draggable
                    onDragStart={handleOrderItemDragStart(id)}
                    onDragOver={handleOrderItemDragOver(index)}
                    onDragEnd={handleDragEnd}
                  >
                    <span className="drag-handle" aria-label={`Drag to reorder ${labelFor(id)}`}>
                      <GripVertical size={14} />
                    </span>
                    <span className="order-item-index">{index + 1}</span>
                    <span className="order-item-title">{labelFor(id)}</span>
                    <button
                      type="button"
                      className="order-item-remove"
                      onClick={() => removeFromOrder(id)}
                      aria-label={`Remove ${labelFor(id)}`}
                    >
                      ×
                    </button>
                  </div>
                </React.Fragment>
              ))
            )}
            {dropIndicatorIndex === orderedSelected.length && dragPayload && <div className="drop-indicator" />}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SOWSectionChecklist;
