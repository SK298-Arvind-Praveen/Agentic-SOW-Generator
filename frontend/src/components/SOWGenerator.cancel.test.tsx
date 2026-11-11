import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import SOWGenerator from './SOWGenerator';
import api from '../services/apiService';
jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn() }));
jest.mock('../contexts/AuthContext', () => ({ useAuth: () => ({ user: { email: 'cancel-test@example.com' }, isAdmin: true }) }));
jest.mock('./CustomTemplateSelector', () => () => null);
jest.mock('./DiagramEditorModal', () => () => null);
jest.mock('../utils/previewChime', () => ({ armPreviewChime: jest.fn(), installPreviewChimeUnlock: () => () => {}, playPreviewReadyChime: jest.fn() }));
jest.mock('../utils/toast', () => ({ toast: { loading: jest.fn(() => 't'), update: jest.fn(), error: jest.fn(), info: jest.fn(), success: jest.fn(), dismiss: jest.fn() } }));
jest.mock('../services/apiService', () => ({ __esModule: true, default: {
  reservePreview: jest.fn(), generatePreview: jest.fn(), cancelPreview: jest.fn(), checkPreviewStatus: jest.fn()
} }));

it('keeps Cancel disabled as Cancelling until the worker acknowledges, then allows another generation', async () => {
  jest.useFakeTimers();
  (api.reservePreview as jest.Mock).mockResolvedValue({ success: true, preview_id: 'p' });
  // Keep the upload response pending: cancellation must still finish independently.
  (api.generatePreview as jest.Mock).mockImplementation(() => new Promise(() => {}));
  (api.cancelPreview as jest.Mock).mockResolvedValue({ success: true, status: 'cancelling' });
  (api.checkPreviewStatus as jest.Mock).mockResolvedValue({ success: true, status: 'generating' });
  const view = render(<SOWGenerator projectId="cancel-ui" accountName="Example" projectName="Example Project" />);
  fireEvent.change(document.querySelector('#authorName')!, { target: { value: 'Author' } });
  fireEvent.change(document.querySelector('#projectObjective')!, { target: { value: 'Create a customer support assistant.' } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Craft SOW Document/i })); });
  expect(screen.getByRole('button', { name: 'Cancel' })).toBeEnabled();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Cancel' })); });
  expect(screen.getByRole('button', { name: /Cancelling/ })).toBeDisabled();
  expect(screen.getByRole('button', { name: /Crafting Your Document/i })).toBeDisabled();
  (api.checkPreviewStatus as jest.Mock).mockResolvedValue({ success: true, status: 'cancelled' });
  await act(async () => { jest.advanceTimersByTime(4000); });
  expect(screen.queryByRole('button', { name: /Cancelling/ })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Craft SOW Document/i })).toBeEnabled();
  expect(api.cancelPreview).toHaveBeenCalledWith('p');
  view.unmount();
  jest.useRealTimers();
});

it('offers only POC and Production in Organization Information and submits the selected type without losing inputs', async () => {
  jest.useFakeTimers();
  (api.reservePreview as jest.Mock).mockResolvedValue({ success: true, preview_id: 'mode-preview' });
  (api.generatePreview as jest.Mock).mockImplementation(() => new Promise(() => {}));
  (api.checkPreviewStatus as jest.Mock).mockResolvedValue({ success: true, status: 'generating' });
  const onModeChange = jest.fn();
  const view = render(<SOWGenerator projectId="mode-selection" selectedMode="poc" onModeChange={onModeChange}
    accountName="Client" projectName="Delivery" />);
  const selector = screen.getByRole('combobox', { name: /SOW Type/ });
  expect(selector.closest('.section-group')).toHaveTextContent('Organization Information');
  expect(Array.from(selector.querySelectorAll('option')).map(option => option.textContent))
    .toEqual(['SOW for POC', 'SOW for Production']);
  fireEvent.change(document.querySelector('#authorName')!, { target: { value: 'Author' } });
  fireEvent.change(document.querySelector('#projectObjective')!, { target: { value: 'Build enterprise help desk.' } });
  fireEvent.change(selector, { target: { value: 'production' } });
  expect(onModeChange).toHaveBeenCalledWith('production');
  expect(document.querySelector('#authorName')).toHaveValue('Author');
  expect(document.querySelector('#projectObjective')).toHaveValue('Build enterprise help desk.');
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: /Craft SOW Document/i })); });
  expect((api.generatePreview as jest.Mock).mock.calls.slice(-1)[0][2]).toBe('production');
  expect(selector).toBeDisabled();
  view.unmount();
  jest.useRealTimers();
});

