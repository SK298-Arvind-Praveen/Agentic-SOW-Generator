import { act, renderHook } from '@testing-library/react';
import { usePageMemoryState } from './usePageMemoryState';

it('retains text and the original uploaded File across navigation/remount', () => {
  const file = new File(['BRD'], 'requirements.docx');
  const first = renderHook(() => usePageMemoryState('navigation-test', { text: '', files: [] as File[] }));
  act(() => first.result.current[1]({ text: 'Half-written objective', files: [file] }));
  first.unmount();
  const second = renderHook(() => usePageMemoryState('navigation-test', { text: '', files: [] as File[] }));
  expect(second.result.current[0].text).toBe('Half-written objective');
  expect(second.result.current[0].files[0]).toBe(file);
});
it('isolates forms and continues receiving updates from a running job after remount', () => {
  const first = renderHook(() => usePageMemoryState('job-test', false));
  const update = first.result.current[1];
  first.unmount();
  const second = renderHook(() => usePageMemoryState('job-test', false));
  const other = renderHook(() => usePageMemoryState('different-user', false));
  act(() => update(true));
  expect(second.result.current[0]).toBe(true);
  expect(other.result.current[0]).toBe(false);
});
