import React, { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import SOWSectionChecklist, { availableSowSectionIds } from './SOWSectionChecklist';
const Harness = () => {
  const [selected, setSelected] = useState(availableSowSectionIds('poc'));
  return <SOWSectionChecklist mode="poc" selected={selected} onChange={setSelected} />;
};
it('starts included and permits exclusion and restoration', () => {
  render(<Harness />);
  const left = screen.getByRole('group', { name: 'Included SOW sections' });
  const right = screen.getByRole('group', { name: 'Excluded SOW sections' });
  expect(within(left).getAllByRole('button')).toHaveLength(availableSowSectionIds('poc').length);
  fireEvent.click(within(left).getByText('Scope of Work'));
  expect(within(right).getByText('Scope of Work')).toBeInTheDocument();
  fireEvent.click(within(right).getByText('Scope of Work'));
  expect(within(left).getByText('Scope of Work')).toBeInTheDocument();
  expect(screen.queryByText('Document Version Control')).not.toBeInTheDocument();
});
it('supports drag to exclude', () => {
  render(<Harness />);
  fireEvent.dragStart(screen.getByText('Scope of Work').closest('button')!, { dataTransfer: { effectAllowed: '' } });
  const right = screen.getByRole('group', { name: 'Excluded SOW sections' });
  fireEvent.drop(right);
  expect(within(right).getByText('Scope of Work')).toBeInTheDocument();
});
it('starts conceptual flow excluded and allows dragging it in and back out', () => {
  render(<Harness />);
  const left = screen.getByRole('group', { name: 'Included SOW sections' });
  const right = screen.getByRole('group', { name: 'Excluded SOW sections' });
  const option = within(right).getByRole('button', { name: 'Conceptual flow diagram' });
  expect(option).toBeEnabled();
  fireEvent.dragStart(option, { dataTransfer: { effectAllowed: '' } });
  fireEvent.drop(left);
  const included = within(left).getByRole('button', { name: 'Conceptual flow diagram' });
  fireEvent.dragStart(included, { dataTransfer: { effectAllowed: '' } });
  fireEvent.drop(right);
  expect(within(right).getByRole('button', { name: 'Conceptual flow diagram' })).toBeInTheDocument();
});

it('inserts conceptual flow before architecture and allows subsequent reordering', () => {
  render(<Harness />);
  const left = screen.getByRole('group', { name: 'Included SOW sections' });
  fireEvent.click(screen.getByText('Conceptual flow diagram'));
  const labels = () => within(left).getAllByRole('button').map(button => button.textContent);
  expect(labels().indexOf('Conceptual flow diagram')).toBe(labels().indexOf('Solution Architecture') - 1);
  fireEvent.dragStart(within(left).getByText('Conceptual flow diagram').closest('button')!, { dataTransfer: { effectAllowed: '' } });
  fireEvent.drop(within(left).getByText('Service Agreement').closest('button')!);
  expect(labels()[0]).toBe('Conceptual flow diagram');
});
