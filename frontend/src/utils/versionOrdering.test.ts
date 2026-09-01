import { latestDocumentForVersion, sortVersionKeysNewestFirst } from './versionOrdering';

describe('SOW version ordering', () => {
  it('orders versions by generation time rather than alphabetically', () => {
    const versions = {
      v1: [{ timestamp: '2026-08-18T10:00:00Z' }],
      v11: [{ timestamp: '2026-08-31T10:00:00Z' }],
      v2: [{ timestamp: '2026-08-19T10:00:00Z' }],
      v13: [{ timestamp: '2026-09-01T10:00:00Z' }],
      v12: [{ timestamp: '2026-08-31T12:00:00Z' }],
    };
    expect(sortVersionKeysNewestFirst(versions)).toEqual(['v13', 'v12', 'v11', 'v2', 'v1']);
  });

  it('selects the latest generated document within one version', () => {
    expect(latestDocumentForVersion([
      { document_id: 'old', timestamp: '2026-08-01T10:00:00Z' },
      { document_id: 'new', timestamp: '2026-08-01T11:00:00Z' },
    ]).document_id).toBe('new');
  });
});
