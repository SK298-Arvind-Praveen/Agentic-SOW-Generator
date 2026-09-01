import { hasProjectScopeSource } from './sowInputValidation';

describe('SOW project source validation', () => {
  it('requires scope text or at least one uploaded document', () => {
    expect(hasProjectScopeSource('', [])).toBe(false);
    expect(hasProjectScopeSource('Short note', [])).toBe(true);
    expect(hasProjectScopeSource('A sufficiently detailed project scope statement.', [])).toBe(true);
    expect(hasProjectScopeSource('', [new File(['BRD'], 'requirements.pdf')])).toBe(true);
  });
});
