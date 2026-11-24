import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';
import apiService from './services/apiService';

test('shows Google sign-in without password or signup', async () => {
  jest.spyOn(apiService, 'getCurrentUser').mockRejectedValue(new Error('Authentication required'));
  render(<App />);
  expect(await screen.findByRole('button', { name: /continue with google/i })).toBeInTheDocument();
  expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/create an account/i)).not.toBeInTheDocument();
  jest.restoreAllMocks();
});
