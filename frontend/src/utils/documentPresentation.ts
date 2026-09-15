import type { Document } from '../services/apiService';

export const documentTimestamp = (record: Partial<Document>): string => (
  record.timestamp || record.created_at || record.date || record.document_date || ''
);

export const formatDocumentDateTime = (value: string | undefined): string => {
  if (!value) return 'N/A';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone: 'Asia/Kolkata',
  }).replace(',', '');
};

export const sowDownloadFilename = (record: Partial<Document>): string => {
  const project = record.project_name || record.name || record.title || 'SOW';
  const mode = record.mode || record.sow_type || record.type || 'POC';
  const version = record.version || 'v1';
  return `${project} - ${mode} ${version}.docx`;
};
