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

test('late prose alignment failure is visible', () => {
  render(<DiagramWarning asset={{status:'review_required', image_base64:'png',
    text_alignment:{error:'Model unavailable during explanation'}}} />);
  expect(screen.getByRole('alert')).toHaveTextContent('Model unavailable during explanation');
});
