import React, { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import SOWSectionChecklist from './SOWSectionChecklist';
import { AuthProvider } from '../contexts/AuthContext';

const Harness: React.FC<{ initial?: string[] }> = ({ initial = [] }) => {
  const [selected, setSelected] = useState(initial);
  return (
    <AuthProvider>
      <SOWSectionChecklist
        mode="poc"
        selected={selected}
        onChange={setSelected}
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
});
