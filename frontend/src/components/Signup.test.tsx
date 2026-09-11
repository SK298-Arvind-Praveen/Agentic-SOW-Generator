import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Signup from './Signup';

jest.mock('../services/apiService', () => ({
  __esModule: true,
  default: { signup: jest.fn(), resendVerification: jest.fn() },
}));

test('shows numeric SK-prefixed employee ID and hides resend before first attempt', () => {
  const { container } = render(<MemoryRouter><Signup /></MemoryRouter>);
  expect(screen.getByText('SK-')).toBeInTheDocument();
  expect(screen.getByRole('spinbutton')).toHaveAttribute('min', '1');
  expect(screen.queryByRole('button', { name: /resend verification/i })).not.toBeInTheDocument();
  expect(container.querySelectorAll('.required-asterisk')).toHaveLength(7);
});
