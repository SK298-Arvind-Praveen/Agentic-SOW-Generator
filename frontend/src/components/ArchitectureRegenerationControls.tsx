import React, { useEffect, useRef, useState } from 'react';
import apiService from '../services/apiService';
import { armPreviewChime, playPreviewReadyChime } from '../utils/previewChime';

interface Props {
  previewId: string;
  disabled?: boolean;
  onBusyChange: (busy: boolean) => void;
  onUpdated: (response: any) => void;
}

export default function ArchitectureRegenerationControls(props: Props) {
  const [instructions, setInstructions] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const callbacks = useRef(props);
  callbacks.current = props;
  const clickLock = useRef(false);
  const starting = useRef(false);
  const acceptedJob = useRef('');
  const applied = useRef('');
  const dismissedFailure = useRef('');
  const mounted = useRef(true);
  const runningJob = useRef('');
  const setRunning = (value: boolean) => {
    clickLock.current = value;
    setBusy(value);
    callbacks.current.onBusyChange(value);
  };

  useEffect(() => {
    mounted.current = true;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const response = await apiService.architectureRegenerationStatus(props.previewId);
        if (cancelled) return;
        if (!response.success) throw new Error(response.error || 'Unable to check regeneration');
        const job = response.job || {};
        // An initial GET can finish after a click but before the POST is accepted.
        // Likewise, ignore a stale GET for the previous job after starting a new one.
        if (starting.current || (acceptedJob.current && job.id !== acceptedJob.current)) {
          if (!cancelled) timer = setTimeout(poll, 2500);
          return;
        }
        setRunning(job.status === 'running');
        if (job.status === 'running') {
          runningJob.current = job.id;
          setMessage(job.message || 'Regenerating architecture…');
        }
        if (job.status === 'failed' && dismissedFailure.current !== job.id) {
          dismissedFailure.current = job.id;
          setError(job.error || 'Regeneration failed. The previous preview was retained.');
          setMessage('');
        }
        if (job.status === 'completed' && applied.current !== job.id) {
          applied.current = job.id;
          callbacks.current.onUpdated(response);
          if (runningJob.current === job.id) void playPreviewReadyChime(`architecture:${job.id}`);
          setMessage('Diagram and affected SOW sections updated.');
          setError('');
        }
      } catch {
        if (!cancelled && clickLock.current) setMessage('Connection interrupted. The server is still working; reconnecting…');
      }
      if (!cancelled) timer = setTimeout(poll, 2500);
    };
    void poll();
    return () => { cancelled = true; mounted.current = false; clearTimeout(timer); };
    // Callback refs avoid restarting polling whenever the parent receives progress.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.previewId]);

  const regenerate = async () => {
    if (clickLock.current || props.disabled) return;
    armPreviewChime();
    setRunning(true);
    starting.current = true;
    acceptedJob.current = '';
    setError('');
    setMessage('Starting architecture regeneration…');
    try {
      const response = await apiService.regenerateArchitecture(props.previewId, instructions);
      if (!mounted.current) return;
      acceptedJob.current = response.job?.id || '';
      runningJob.current = acceptedJob.current;
      if (!response.success) {
        setRunning(false);
        setError(response.error || 'Unable to start regeneration');
      }
    } catch (e) {
      // POST may have reached the server despite a lost response. Polling resolves
      // whether a job exists; do not start another generation automatically.
      if (mounted.current) setError(e instanceof Error ? e.message : 'Unable to start regeneration');
    } finally {
      starting.current = false;
    }
  };

  return <div className="architecture-regeneration" style={{ margin: '12px 0' }}>
    <label htmlFor={`architecture-changes-${props.previewId}`}>Requested diagram changes (optional)</label>
    <textarea id={`architecture-changes-${props.previewId}`} value={instructions} maxLength={4000}
      disabled={busy || props.disabled} rows={3} style={{ display: 'block', width: '100%', margin: '8px 0' }}
      placeholder="For example: put the application in private subnets and keep Bedrock outside the VPC."
      onChange={event => setInstructions(event.target.value)} />
    <button type="button" className="modal-btn modal-btn-primary" onClick={regenerate} disabled={busy || props.disabled}>
      {busy ? 'Regenerating…' : 'Regenerate diagram'}
    </button>
    <p style={{ fontSize: '13px', color: '#64748b' }}>Updates the diagram and affected SOW text together. You can close the preview while it runs.</p>
    {message && <p role="status" aria-live="polite">{message}</p>}
    {error && <div role="alert" style={{ color: '#b91c1c' }}>{error} <button type="button" aria-label="Dismiss regeneration error" onClick={() => setError('')}>×</button></div>}
  </div>;
}
