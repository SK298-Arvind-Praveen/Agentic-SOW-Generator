import React from 'react';
import { Check } from 'lucide-react';
import './SOWSectionChecklist.css';

export type GeneratorMode = 'poc' | 'production' | 'poc-to-production';

type SectionOption = {
  id: string;
  label: string;
  modes: GeneratorMode[];
};

const ALL_MODES: GeneratorMode[] = ['poc', 'production', 'poc-to-production'];

export const SOW_SECTION_OPTIONS: SectionOption[] = [
  { id: 'about_shellkode', label: 'About Shellkode', modes: ALL_MODES },
  { id: 'about_client', label: 'About Client', modes: ALL_MODES },
  { id: 'project_overview', label: 'Project Overview', modes: ALL_MODES },
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

const SOWSectionChecklist: React.FC<SOWSectionChecklistProps> = ({ mode, selected, onChange }) => {
  const availableOptions = SOW_SECTION_OPTIONS.filter(option => option.modes.includes(mode));
  const availableIds = availableOptions.map(option => option.id);
  const selectedSet = new Set(selected);

  const toggle = (sectionId: string) => {
    const next = new Set(selectedSet);
    if (next.has(sectionId)) next.delete(sectionId);
    else next.add(sectionId);
    onChange(availableIds.filter(id => next.has(id)));
  };

  return (
    <div className="sow-section-checklist" aria-labelledby="sow-section-checklist-title">
      <div className="checklist-heading-row">
        <div>
          <div id="sow-section-checklist-title" className="field-label">Customise SOW sections</div>
          <p className="checklist-help">Choose what the AI should generate. Unchecked topics are omitted from the content and table of contents.</p>
        </div>
        <div className="checklist-actions" aria-label="Section selection actions">
          <span className="checklist-count">{selected.filter(id => availableIds.includes(id)).length} of {availableIds.length} selected</span>
          <button type="button" onClick={() => onChange(availableIds)}>Select all</button>
          <button type="button" onClick={() => onChange([])}>Clear all</button>
        </div>
      </div>

      <div className="checklist-grid">
        {availableOptions.map(option => {
          const checked = selectedSet.has(option.id);
          return (
            <label className={`checklist-option ${checked ? 'selected' : ''}`} key={option.id}>
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(option.id)}
              />
              <span className="custom-checkbox" aria-hidden="true">{checked && <Check size={12} />}</span>
              <span className="checklist-option-title">{option.label}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
};

export default SOWSectionChecklist;
