import React, { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import SOWSectionChecklist, { availableSowSectionIds } from './SOWSectionChecklist';
import apiService from '../services/apiService';
import { AuthProvider } from '../contexts/AuthContext';

const Harness: React.FC<{ initial?: string[]; custom?: any[] }> = ({ initial = [], custom = [] }) => {
  const [selected, setSelected] = useState(initial);
  const [timelineFormat, setTimelineFormat] = useState<'table' | 'gantt'>('table');
  return (
    <AuthProvider>
      <SOWSectionChecklist
        mode="poc"
        selected={selected}
        onChange={setSelected}
        extractedSections={custom}
        timelineFormat={timelineFormat}
        onTimelineFormatChange={setTimelineFormat}
      />
    </AuthProvider>
  );
};

const dataTransfer = () => ({
  effectAllowed: '',
  dropEffect: '',
  files: [],
  items: [],
  types: [],
  clearData: jest.fn(),
  getData: jest.fn(),
  setData: jest.fn(),
  setDragImage: jest.fn(),
});

describe('SOWSectionChecklist', () => {
  it('removes Open Clarifications from defaults and saved selections', () => {
    for (const mode of ['poc', 'production', 'poc-to-production'] as const) {
      expect(availableSowSectionIds(mode)).not.toContain('open_clarifications');
    }
    render(<Harness initial={['open_clarifications', 'scope_of_work']} />);
    expect(screen.queryByText('Open Clarifications')).not.toBeInTheDocument();
    expect(screen.getByText('1 selected')).toBeInTheDocument();
  });

  it('does not restore Open Clarifications from the API or extracted templates', async () => {
    const fetch = jest.spyOn(apiService, 'fetchSowSections').mockResolvedValue({success: true, sections: [
      {id: 'open_clarifications', label: 'Open Clarifications', modes: ['poc']},
      {id: 'scope_of_work', label: 'Scope of Work', modes: ['poc']},
    ]} as any);
    try {
      render(<Harness custom={[{id: 'custom_open', label: 'Open Clarifications', modes: ['poc']}]} />);
      await screen.findByRole('button', {name: 'Scope of Work'});
      expect(screen.queryByText('Open Clarifications')).not.toBeInTheDocument();
    } finally {
      fetch.mockRestore();
    }
  });

  it('shows the Table/Gantt selector only when Project Timeline is selected', () => {
    const { container } = render(<Harness />);
    expect(screen.queryByRole('radio', { name: 'Gantt chart' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Project Timeline' }));
    expect(screen.getByRole('radio', { name: 'Table' })).toBeChecked();
    fireEvent.click(screen.getByRole('radio', { name: 'Gantt chart' }));
    expect(screen.getByRole('radio', { name: 'Gantt chart' })).toBeChecked();
    const checklist = container.querySelector('.sow-section-checklist')!;
    const formatPanel = screen.getByRole('group', { name: 'Project Timeline format' });
    expect(checklist.contains(formatPanel)).toBe(false);
    expect(checklist.compareDocumentPosition(formatPanel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
  it('shows plain Available buttons and Selected wording', () => {
    const { container } = render(<Harness />);

    expect(screen.getByText(
      'Click or drag a section from Available into Selected to include it in your SOW, and feel free to rearrange it as needed.'
    )).toBeInTheDocument();
    expect(screen.getByText('Selected SOW sections')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'AWS Pricing' }));
    fireEvent.click(screen.getByRole('button', { name: 'Objective' }));

    expect(screen.getByText('2 selected')).toBeInTheDocument();
    expect(Array.from(
      container.querySelectorAll<HTMLElement>('.order-item-title')
    ).map(node => node.textContent)).toEqual(['AWS Pricing', 'Objective']);
  });

  it('reorders Selected sections using drag and drop', () => {
    const { container } = render(
      <Harness initial={['aws_pricing', 'project_overview', 'scope_of_work']} />
    );
    const rows = Array.from(container.querySelectorAll<HTMLElement>('.order-item'));
    const selectedPanel = container.querySelector<HTMLElement>('.order-list');
    expect(selectedPanel).not.toBeNull();

    const transfer = dataTransfer();
    fireEvent.dragStart(rows[2], { dataTransfer: transfer });
    fireEvent.dragOver(rows[0], { dataTransfer: transfer });
    fireEvent.drop(selectedPanel!, { dataTransfer: transfer });

    const orderedTitles = Array.from(
      container.querySelectorAll<HTMLElement>('.order-item-title')
    ).map(node => node.textContent);
    expect(orderedTitles).toEqual(['Scope of Work', 'AWS Pricing', 'Objective']);
    expect(within(selectedPanel!).getByText('Scope of Work')).toBeInTheDocument();
  });

  it('offers Document Version Control as an orderable section', () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole('button', { name: 'Document Version Control' }));

    expect(screen.getByText('1 selected')).toBeInTheDocument();
    expect(screen.getByText('Document Version Control', { selector: '.order-item-title' })).toBeInTheDocument();
  });

  it('shows extracted sections separately and mixes them with standard sections', () => {
    const { container } = render(
      <Harness custom={[{
        id: 'custom_abcd_governance', label: 'Governance Model',
        modes: ['poc', 'production', 'poc-to-production'], order: 0,
      }]} />
    );
    expect(screen.getByText('Custom extracted sections')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Objective' }));
    fireEvent.click(screen.getByRole('button', { name: 'Governance Model' }));
    expect(Array.from(container.querySelectorAll<HTMLElement>('.order-item-title')).map(
      node => node.textContent
    )).toEqual(['Objective', 'Governance Model']);
  });
});
