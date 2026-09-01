import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders the login route for an unauthenticated user', () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: /sow management portal/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /sign in to dashboard/i })).toBeInTheDocument();
});
