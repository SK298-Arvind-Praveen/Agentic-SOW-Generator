import { Dispatch, SetStateAction, useCallback, useSyncExternalStore } from 'react';

// Deliberately memory-only: File objects survive SPA navigation, but refresh
// clears the form. Keys include user/project/mode to prevent cross-form leakage.
const values = new Map<string, unknown>();
const listeners = new Map<string, Set<() => void>>();
export const readPageMemory = <T,>(key: string): T | undefined => values.get(key) as T | undefined;

export function usePageMemoryState<T>(key: string, initial: T | (() => T)): [T, Dispatch<SetStateAction<T>>] {
  if (!values.has(key)) values.set(key, typeof initial === 'function' ? (initial as () => T)() : initial);
  const subscribe = useCallback((listener: () => void) => {
    const set = listeners.get(key) || new Set<() => void>();
    listeners.set(key, set);
    set.add(listener);
    return () => { set.delete(listener); };
  }, [key]);
  const snapshot = useCallback(() => values.get(key) as T, [key]);
  const value = useSyncExternalStore(subscribe, snapshot, snapshot);
  const update = useCallback<Dispatch<SetStateAction<T>>>((next) => {
    values.set(key, typeof next === 'function' ? (next as (previous: T) => T)(values.get(key) as T) : next);
    listeners.get(key)?.forEach(listener => listener());
  }, [key]);
  return [value, update];
}
