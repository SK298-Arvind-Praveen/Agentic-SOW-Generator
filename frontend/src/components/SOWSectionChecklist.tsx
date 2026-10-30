import { GripVertical } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import './SOWSectionChecklist.css';
export type GeneratorMode = 'poc' | 'production' | 'poc-to-production';

export type SectionOption = {
  id: string;
  label: string;
  modes: GeneratorMode[];
  prompt?: string;
  custom?: boolean;
};

const ALL_MODES: GeneratorMode[] = ['poc', 'production', 'poc-to-production'];

export const SOW_SECTION_OPTIONS: SectionOption[] = [
  { id: 'service_agreement', label: 'Service Agreement', modes: ALL_MODES },
  { id: 'about_shellkode', label: 'About Shellkode', modes: ALL_MODES },
  { id: 'about_client', label: 'About Client', modes: ALL_MODES },
  { id: 'project_overview', label: 'Objective', modes: ALL_MODES },
  { id: 'business_benefits', label: 'Business Benefits', modes: ALL_MODES },
  { id: 'architecture_diagram', label: 'Solution Architecture', modes: ALL_MODES },
  { id: 'scope_of_work', label: 'Scope of Work', modes: ALL_MODES },
  { id: 'customer_dependencies', label: 'Customer Dependencies', modes: ALL_MODES },
  { id: 'assumptions', label: 'Assumptions', modes: ALL_MODES },
  { id: 'out_of_scope', label: 'Out of Scope', modes: ALL_MODES },
  { id: 'timelines_deliverables', label: 'Project Timeline', modes: ALL_MODES },
  { id: 'aws_pricing', label: 'AWS Pricing', modes: ALL_MODES },
  { id: 'customer_responsibilities', label: 'Customer Responsibilities', modes: ALL_MODES },
  { id: 'project_team_effort', label: 'Project Team Effort', modes: ALL_MODES },
  { id: 'success_criteria', label: 'Success Criteria', modes: ALL_MODES },
  { id: 'raci_matrix', label: 'Roles and Responsibilities', modes: ALL_MODES },
  { id: 'change_order', label: 'Change Order', modes: ALL_MODES },
  { id: 'project_plan_termination', label: 'Project Plan Termination', modes: ALL_MODES },
  { id: 'contacts_reporting', label: 'Contacts and Reporting', modes: ALL_MODES },
  { id: 'marketing_authorization', label: 'Marketing Authorization', modes: ALL_MODES },
  { id: 'terms_conditions', label: 'Terms & Conditions', modes: ALL_MODES },
  { id: 'acceptance_signatories', label: 'Acceptance and Signatories', modes: ALL_MODES },
];

export const availableSowSectionIds = (mode: GeneratorMode): string[] =>
  SOW_SECTION_OPTIONS.filter(option => option.modes.includes(mode)).map(option => option.id);

interface SOWSectionChecklistProps {
  mode: GeneratorMode;
  selected: string[];
  onChange: (sectionIds: string[]) => void;
  extractedSections?: SectionOption[];
  timelineFormat?: 'table' | 'gantt';
  onTimelineFormatChange?: (format: 'table' | 'gantt') => void;
}

const SOWSectionChecklist: React.FC<SOWSectionChecklistProps> = ({ mode, selected, onChange, timelineFormat = 'table', onTimelineFormatChange }) => {
  const sections = [
    ...SOW_SECTION_OPTIONS.filter(option => option.modes.includes(mode)),
    { id: 'conceptual_flow_diagram', label: 'Conceptual flow diagram', modes: ALL_MODES },
  ];
  const [dragId, setDragId] = useState<string | null>(null);
  useEffect(() => {
    const cleaned = selected.filter(id => id !== 'document_version_control' && id !== 'open_clarifications');
    if (cleaned.length !== selected.length) onChange(cleaned);
  }, [selected, onChange]);
  const move = (id: string, include: boolean) => {
    const next = selected.filter(value => value !== id);
    if (include) {
      const architectureIndex = next.indexOf('architecture_diagram');
      next.splice(id === 'conceptual_flow_diagram' && architectureIndex >= 0 ? architectureIndex : next.length, 0, id);
    }
    onChange(next);
    setDragId(null);
  };
  return (
    <>
      <section className="sow-section-checklist" aria-label="Customise SOW sections">
        <div className="field-label">Customise SOW sections</div>
        <p className="checklist-help">Standard sections are included by default; Conceptual flow diagram is optional. Click or drag sections between the boxes to include or exclude them.</p>
        <div className="checklist-two-panel">
          {[true, false].map(include => (
            <div className="checklist-panel" key={String(include)}>
              <div className="checklist-panel-title">{include ? 'Included SOW sections' : 'Excluded SOW sections'}</div>
              <div className="checklist-panel-body checklist-list" role="group" aria-label={include ? 'Included SOW sections' : 'Excluded SOW sections'}
                onDragOver={event => event.preventDefault()}
                onDrop={event => { event.preventDefault(); if (dragId) move(dragId, include); }}>
                {(include ? selected.map(id => sections.find(section => section.id === id)).filter((section): section is SectionOption => !!section)
                  : sections.filter(section => !selected.includes(section.id))).map(section => (
                  <button type="button" className="checklist-option" key={section.id} draggable
                    onDragStart={event => { setDragId(section.id); event.dataTransfer.effectAllowed = 'move'; }}
                    onDragOver={event => event.preventDefault()}
                    onDrop={event => {
                      if (include && dragId && selected.includes(dragId)) {
                        event.preventDefault(); event.stopPropagation();
                        if (dragId !== section.id) {
                          const next = selected.filter(id => id !== dragId);
                          next.splice(next.indexOf(section.id), 0, dragId);
                          onChange(next);
                        }
                        setDragId(null);
                      }
                    }}
                    onDragEnd={() => setDragId(null)} onClick={() => move(section.id, !include)}>
                    <span className="checklist-option-title">{section.label}</span>
                    <span className="drag-handle" aria-hidden="true"><GripVertical size={14} /></span>
                  </button>
                ))}
                {!sections.some(section => selected.includes(section.id) === include) &&
                  <p className="order-empty-message">{include ? 'Drag sections here to include them.' : 'Drag sections here to exclude them.'}</p>}
              </div>
            </div>
          ))}
        </div>
      </section>
      {selected.includes('timelines_deliverables') && onTimelineFormatChange && (
        <div className="timeline-options-panel" role="group" aria-label="Project Timeline format">
          <h3>Project Timeline format</h3>
          <p>Choose how the project schedule appears in the SOW.</p>
          <div className="timeline-format-options">
            {(['table', 'gantt'] as const).map(format => (
              <label key={format}>
                <input type="radio" name="timeline-format" value={format} checked={timelineFormat === format}
                  onChange={() => onTimelineFormatChange(format)} />
                {format === 'table' ? 'Table' : 'Gantt chart'}
              </label>
            ))}
          </div>
        </div>
      )}
    </>
  );
};

export default SOWSectionChecklist;
