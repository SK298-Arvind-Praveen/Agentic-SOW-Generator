import { latestDocumentForVersion, sortVersionKeysNewestFirst } from './versionOrdering';

describe('SOW version ordering', () => {
  it('orders versions numerically rather than alphabetically or by mixed date formats', () => {
    const versions = {
      v1: [{ timestamp: '2026-08-18T10:00:00Z' }],
      v11: [{ timestamp: '2026-08-31T10:00:00Z' }],
      v2: [{ timestamp: '2026-08-19T10:00:00Z' }],
      v13: [{ timestamp: '2026-09-01T10:00:00Z' }],
      v12: [{ timestamp: '2026-08-31T12:00:00Z' }],
    };
    expect(sortVersionKeysNewestFirst(versions)).toEqual(['v13', 'v12', 'v11', 'v2', 'v1']);
  });

  it('keeps v20 and v19 above timestamped v18', () => {
    const versions = {
      v18: [{ timestamp: '2026-09-15T15:25:12Z' }],
      v20: [{ document_date: '15 September 2026' }],
      v19: [{ document_date: '15 September 2026' }],
    };
    expect(sortVersionKeysNewestFirst(versions)).toEqual(['v20', 'v19', 'v18']);
  });

  it('selects the latest generated document within one version', () => {
    expect(latestDocumentForVersion([
      { document_id: 'old', timestamp: '2026-08-01T10:00:00Z' },
      { document_id: 'new', timestamp: '2026-08-01T11:00:00Z' },
    ]).document_id).toBe('new');
  });
});
