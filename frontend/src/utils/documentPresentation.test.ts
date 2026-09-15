import { documentTimestamp, formatDocumentDateTime, sowDownloadFilename } from './documentPresentation';

describe('document presentation', () => {
  it('prefers a generated timestamp over a date-only document date', () => {
    expect(documentTimestamp({
      timestamp: '2026-09-15T17:38:00+05:30',
      document_date: '2026-09-15',
    })).toBe('2026-09-15T17:38:00+05:30');
  });

  it('formats date and time in the records format', () => {
    expect(formatDocumentDateTime('2026-09-15T17:38:00+05:30')).toMatch(/^15\/09\/26 17:38$/);
  });

  it('builds a readable versioned SOW filename', () => {
    expect(sowDownloadFilename({
      project_name: 'Tata CLiQ | AI / Agentic Customer Support Platform',
      mode: 'POC',
      version: 'v20',
    })).toBe('Tata CLiQ | AI / Agentic Customer Support Platform - POC v20.docx');
  });
});
