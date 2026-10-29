import React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import apiService from '../services/apiService';
import ArchitectureRegenerationControls from './ArchitectureRegenerationControls';
import { playPreviewReadyChime } from '../utils/previewChime';
jest.mock('../utils/previewChime', () => ({ armPreviewChime: jest.fn(), playPreviewReadyChime: jest.fn() }));

jest.mock('../services/apiService', () => ({ __esModule: true, default: {
  regenerateArchitecture: jest.fn(), architectureRegenerationStatus: jest.fn(),
} }));
const status = apiService.architectureRegenerationStatus as jest.Mock;
const start = apiService.regenerateArchitecture as jest.Mock;
beforeEach(() => { jest.useFakeTimers(); jest.clearAllMocks(); status.mockResolvedValue({ success: true, job: {} }); });
afterEach(() => { jest.useRealTimers(); });

test('double click submits once with optional instructions', async () => {
  start.mockResolvedValue({ success: true, job: { status: 'running' } });
  render(<ArchitectureRegenerationControls previewId="p1" onBusyChange={jest.fn()} onUpdated={jest.fn()} />);
  await act(async () => {});
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Use private subnets' } });
  const button = screen.getByRole('button', { name: 'Regenerate diagram' });
  fireEvent.click(button); fireEvent.click(button);
  await act(async () => {});
  expect(start).toHaveBeenCalledTimes(1);
  expect(start).toHaveBeenCalledWith('p1', 'Use private subnets');
});

test('reopening attaches to a running job and applies completed content', async () => {
  const updated = jest.fn();
  status.mockResolvedValueOnce({ success: true, job: { id: 'j', status: 'running', message: 'Checking diagram' } })
    .mockResolvedValue({ success: true, job: { id: 'j', status: 'completed' }, content: { architecture_diagram: '- New' } });
  render(<ArchitectureRegenerationControls previewId="p1" onBusyChange={jest.fn()} onUpdated={updated} />);
  await act(async () => {});
  expect(screen.getByRole('button', { name: 'Regenerating…' })).toBeDisabled();
  await act(async () => { jest.advanceTimersByTime(2500); });
  expect(updated).toHaveBeenCalledTimes(1);
  expect(start).not.toHaveBeenCalled();
  expect(playPreviewReadyChime).toHaveBeenCalledWith('architecture:j');
  await act(async () => { jest.advanceTimersByTime(2500); });
  expect(playPreviewReadyChime).toHaveBeenCalledTimes(1);
});

test('failure persists until dismissed and never replaces preview', async () => {
  const updated = jest.fn();
  status.mockResolvedValue({ success: true, job: { id: 'j', status: 'failed', error: 'Diagram failed validation' } });
  render(<ArchitectureRegenerationControls previewId="p1" onBusyChange={jest.fn()} onUpdated={updated} />);
  await act(async () => {});
  expect(screen.getByRole('alert')).toHaveTextContent('Diagram failed validation');
  expect(updated).not.toHaveBeenCalled();
  expect(playPreviewReadyChime).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss regeneration error' }));
  await act(async () => { jest.advanceTimersByTime(2500); });
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

test('reopening an already completed regeneration does not replay the chime', async () => {
  status.mockResolvedValue({ success: true, job: { id: 'old-job', status: 'completed' }, content: {} });
  render(<ArchitectureRegenerationControls previewId="p1" onBusyChange={jest.fn()} onUpdated={jest.fn()} />);
  await act(async () => {});
  expect(playPreviewReadyChime).not.toHaveBeenCalled();
});

test('a GET started before the click cannot release the POST click lock', async () => {
  let finishGet: (value: any) => void = () => {};
  let finishPost: (value: any) => void = () => {};
  status.mockReturnValueOnce(new Promise(resolve => { finishGet = resolve; }));
  start.mockReturnValueOnce(new Promise(resolve => { finishPost = resolve; }));
  render(<ArchitectureRegenerationControls previewId="p1" onBusyChange={jest.fn()} onUpdated={jest.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: 'Regenerate diagram' }));
  await act(async () => { finishGet({ success: true, job: {} }); });
  expect(screen.getByRole('button', { name: 'Regenerating…' })).toBeDisabled();
  await act(async () => { finishPost({ success: true, job: { id: 'j', status: 'running' } }); });
  expect(start).toHaveBeenCalledTimes(1);
});
