import React from 'react';
import { Check, Lock } from 'lucide-react';
import './SOWSectionChecklist.css';

export type GeneratorMode = 'poc' | 'production' | 'poc-to-production';

type SectionOption = {
  id: string;
  label: string;
  description: string;
  group: 'Scope' | 'Delivery' | 'Technical' | 'Commercial & Governance';
  modes: GeneratorMode[];
};

const ALL_MODES: GeneratorMode[] = ['poc', 'production', 'poc-to-production'];
const PRODUCTION_MODES: GeneratorMode[] = ['production', 'poc-to-production'];

export const SOW_SECTION_OPTIONS: SectionOption[] = [
  { id: 'background_context', label: 'Background & current state', description: 'Business context, existing position and prior outcomes.', group: 'Scope', modes: ALL_MODES },
  { id: 'detailed_scope', label: 'Detailed scope of work', description: 'Workstreams, requirements, deliverables and boundaries.', group: 'Scope', modes: ALL_MODES },
  { id: 'solution_architecture', label: 'Solution architecture', description: 'Technical design, integrations, data flow and AWS services.', group: 'Technical', modes: ALL_MODES },
  { id: 'data_migration', label: 'Data migration & readiness', description: 'Migration inputs, reconciliation and readiness activities.', group: 'Technical', modes: PRODUCTION_MODES },
  { id: 'security_compliance', label: 'Security & compliance', description: 'Security, privacy, regulatory and control requirements.', group: 'Technical', modes: PRODUCTION_MODES },
  { id: 'deployment_cutover', label: 'Deployment & cutover', description: 'Release, migration, rollback and production transition.', group: 'Technical', modes: PRODUCTION_MODES },
  { id: 'timeline', label: 'Timeline', description: 'Phases, milestones, deliverables and duration.', group: 'Delivery', modes: ALL_MODES },
  { id: 'project_team_effort', label: 'Project team effort', description: 'Delivery roles, resource counts and effort basis.', group: 'Delivery', modes: ['poc'] },
  { id: 'testing_acceptance', label: 'Testing & acceptance', description: 'Test approach, validation evidence and acceptance plan.', group: 'Delivery', modes: PRODUCTION_MODES },
  { id: 'success_criteria', label: 'Success criteria', description: 'Observable outcomes and validation evidence.', group: 'Delivery', modes: ALL_MODES },
  { id: 'risks_mitigations', label: 'Risks & mitigations', description: 'Delivery risks, impacts, owners and responses.', group: 'Delivery', modes: PRODUCTION_MODES },
  { id: 'operations_support', label: 'Operations & support', description: 'Day-2 ownership, monitoring and support boundaries.', group: 'Delivery', modes: PRODUCTION_MODES },
  { id: 'pricing', label: 'Pricing', description: 'AWS consumption and implementation-cost basis.', group: 'Commercial & Governance', modes: ALL_MODES },
  { id: 'assumptions_dependencies', label: 'Assumptions & dependencies', description: 'Planning conditions, inputs, access and external dependencies.', group: 'Commercial & Governance', modes: ALL_MODES },
  { id: 'open_clarifications', label: 'Open clarifications', description: 'Material unanswered questions and confirmation requests.', group: 'Commercial & Governance', modes: ALL_MODES },
  { id: 'out_of_scope', label: 'Out of scope', description: 'Explicit exclusions and deferred capabilities.', group: 'Commercial & Governance', modes: ALL_MODES },
  { id: 'customer_responsibilities', label: 'Customer responsibilities', description: 'Customer-provided inputs, access, reviews and approvals.', group: 'Commercial & Governance', modes: PRODUCTION_MODES },
  { id: 'governance_terms', label: 'Governance & terms', description: 'Change management, reporting, termination and terms.', group: 'Commercial & Governance', modes: PRODUCTION_MODES },
  { id: 'signatures', label: 'Signatures at the end', description: 'Blank acceptance and signatory block.', group: 'Commercial & Governance', modes: ALL_MODES },
];

export const availableSowSectionIds = (mode: GeneratorMode): string[] =>
  SOW_SECTION_OPTIONS.filter(option => option.modes.includes(mode)).map(option => option.id);

const MANDATORY_SECTIONS = [
  'Front page',
  'Version control',
  'Table of contents',
  'Project scope overview',
];

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

  const groups: SectionOption['group'][] = ['Scope', 'Delivery', 'Technical', 'Commercial & Governance'];

  return (
    <div className="sow-section-checklist" aria-labelledby="sow-section-checklist-title">
      <div className="checklist-heading-row">
        <div>
          <div id="sow-section-checklist-title" className="field-label">Customise SOW sections</div>
          <p className="checklist-help">Choose what the AI should generate. Unchecked topics are omitted from the content and table of contents.</p>
        </div>
        <div className="checklist-actions" aria-label="Section selection actions">
          <span className="checklist-count">{selected.filter(id => availableIds.includes(id)).length} of {availableIds.length} optional</span>
          <button type="button" onClick={() => onChange(availableIds)}>Select all</button>
          <button type="button" onClick={() => onChange([])}>Clear optional</button>
        </div>
      </div>

      <div className="mandatory-sections" aria-label="Always included sections">
        <span className="mandatory-label"><Lock size={11} /> Always included</span>
        {MANDATORY_SECTIONS.map(section => <span className="mandatory-chip" key={section}>{section}</span>)}
      </div>

      <div className="checklist-groups">
        {groups.map(group => {
          const options = availableOptions.filter(option => option.group === group);
          if (!options.length) return null;
          return (
            <fieldset className="checklist-group" key={group}>
              <legend>{group}</legend>
              <div className="checklist-grid">
                {options.map(option => {
                  const checked = selectedSet.has(option.id);
                  return (
                    <label className={`checklist-option ${checked ? 'selected' : ''}`} key={option.id}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggle(option.id)}
                      />
                      <span className="custom-checkbox" aria-hidden="true">{checked && <Check size={12} />}</span>
                      <span className="checklist-option-copy">
                        <span className="checklist-option-title">{option.label}</span>
                        <span className="checklist-option-description">{option.description}</span>
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
          );
        })}
      </div>
    </div>
  );
};

export default SOWSectionChecklist;
