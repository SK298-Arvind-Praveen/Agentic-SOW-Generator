import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import DiagramWarning from './DiagramWarning';

test('retained diagram displays its failure and reason', () => {
  render(<DiagramWarning asset={{ status: 'review_required', image_base64: 'png',
    quality_warnings: ['Connector route failed', 'Connector route failed'] }} />);
  expect(screen.getByRole('alert')).toHaveTextContent('Diagram needs review');
  expect(screen.getByRole('alert')).toHaveTextContent('included in the download');
  expect(screen.getAllByText('Connector route failed')).toHaveLength(1);
});

test('a clean diagram does not show a warning', () => {
  render(<DiagramWarning asset={{status:'ready', image_base64:'png'}} />);
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test('minor layout advisories are available in collapsed notes without claiming review failed', () => {
  render(<DiagramWarning asset={{status:'ready', image_base64:'png',
    layout_advisories:['Connector touches a readable heading.']}} />);
  expect(screen.getByRole('note')).toHaveTextContent('Connector touches a readable heading.');
  expect(screen.getByText('Layout notes (1)').closest('details')).not.toHaveAttribute('open');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(screen.queryByText('Diagram needs review')).not.toBeInTheDocument();
});

test('late prose alignment failure is visible', () => {
  render(<DiagramWarning asset={{status:'review_required', image_base64:'png',
    text_alignment:{error:'Model unavailable during explanation'}}} />);
  expect(screen.getByRole('alert')).toHaveTextContent('Model unavailable during explanation');
});

test('warning starts collapsed and removes generic review summaries', () => {
  render(<DiagramWarning asset={{status:'review_required', quality_warnings:[
    'Overview image review found visual issues; see diagram diagnostics',
    'Image review found visual defects', 'SAP connector is detached']}} />);
  expect(screen.getByText('Diagram needs review').closest('details')).not.toHaveAttribute('open');
  expect(screen.queryByText('Image review found visual defects')).not.toBeInTheDocument();
  expect(screen.queryByText('Overview image review found visual issues; see diagram diagnostics')).not.toBeInTheDocument();
  expect(screen.getByText('SAP connector is detached')).toBeInTheDocument();
});
