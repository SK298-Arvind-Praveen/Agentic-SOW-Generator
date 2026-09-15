const versionNumber = (value: string): number => {
  const match = String(value).match(/\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : -1;
};

const generatedAt = (document: any): number => {
  const value = document?.timestamp || document?.created_at || document?.document_date || document?.date;
  const parsed = value ? new Date(value).getTime() : NaN;
  return Number.isFinite(parsed) ? parsed : 0;
};

export const latestDocumentForVersion = (value: any): any => {
  if (!Array.isArray(value)) return value;
  return [...value].sort((a, b) => generatedAt(b) - generatedAt(a))[0];
};

export const sortVersionKeysNewestFirst = (versionMap: Record<string, any>): string[] => (
  Object.keys(versionMap).sort((a, b) => {
    // Version is the authoritative sequence. Timestamps are only a tie-breaker
    // because older records contain mixed date-only and full timestamp values.
    const versionDifference = versionNumber(b) - versionNumber(a);
    if (versionDifference) return versionDifference;
    const dateDifference = generatedAt(latestDocumentForVersion(versionMap[b]))
      - generatedAt(latestDocumentForVersion(versionMap[a]));
    return dateDifference;
  })
);
