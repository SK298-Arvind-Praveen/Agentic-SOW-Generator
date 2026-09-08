export const formatTokenCount = (value: number | string | null | undefined): string => {
  if (value === null || value === undefined || value === '') return '—';
  const tokens = Number(value);
  if (!Number.isFinite(tokens) || tokens < 0) return '—';
  return Math.trunc(tokens).toLocaleString('en-US');
};
