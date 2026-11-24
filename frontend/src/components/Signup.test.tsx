import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Signup from './Signup';

test('old signup links return to Google login', async () => {
  render(<MemoryRouter initialEntries={['/signup']}><Routes>
    <Route path="/signup" element={<Signup />} />
    <Route path="/login" element={<div>Google login</div>} />
  </Routes></MemoryRouter>);
  expect(await screen.findByText('Google login')).toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});
