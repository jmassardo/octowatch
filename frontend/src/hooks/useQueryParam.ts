import { useCallback } from 'react';
import { useSearchParams } from 'react-router';

type SetParam = (value: string, options?: { replace?: boolean }) => void;
type SetNumParam = (value: number, options?: { replace?: boolean }) => void;

/**
 * Sync a single string query param to the URL.
 * Omits the param when value equals defaultValue to keep URLs clean.
 * Defaults to push (replace: false) so back/forward navigation works.
 */
export function useQueryParam(key: string, defaultValue: string): [string, SetParam] {
  const [searchParams, setSearchParams] = useSearchParams();
  const value = searchParams.get(key) ?? defaultValue;

  const setValue: SetParam = useCallback(
    (newValue, opts) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (newValue === defaultValue) {
            next.delete(key);
          } else {
            next.set(key, newValue);
          }
          return next;
        },
        { replace: opts?.replace ?? false },
      );
    },
    [key, defaultValue, setSearchParams],
  );

  return [value, setValue];
}

/**
 * Like useQueryParam but restricted to a known set of valid values.
 * Invalid/unknown URL values fall back to defaultValue.
 */
export function useEnumQueryParam<T extends string>(
  key: string,
  validValues: readonly T[],
  defaultValue: T,
): [T, (value: T, options?: { replace?: boolean }) => void] {
  const [raw, setRaw] = useQueryParam(key, defaultValue);
  const value: T = (validValues as readonly string[]).includes(raw) ? (raw as T) : defaultValue;

  const setValue = useCallback((v: T, opts?: { replace?: boolean }) => setRaw(v, opts), [setRaw]);

  return [value, setValue];
}

/**
 * Sync a numeric query param (e.g. page number).
 * Returns defaultValue for non-numeric or negative URL values.
 */
export function useQueryParamInt(key: string, defaultValue: number): [number, SetNumParam] {
  const [raw, setRaw] = useQueryParam(key, String(defaultValue));
  const parsed = parseInt(raw, 10);
  const value = isNaN(parsed) || parsed < 1 ? defaultValue : parsed;

  const setNum: SetNumParam = useCallback((v, opts) => setRaw(String(v), opts), [setRaw]);

  return [value, setNum];
}

/**
 * Batch-update multiple query params atomically.
 * Pass null to remove a param. Preserves params not mentioned in updates.
 */
export function useSetQueryParams(): (
  updates: Record<string, string | number | null | undefined>,
  options?: { replace?: boolean },
) => void {
  const [, setSearchParams] = useSearchParams();

  return useCallback(
    (updates, opts) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [k, v] of Object.entries(updates)) {
            if (v === null || v === undefined || v === '') {
              next.delete(k);
            } else {
              next.set(k, String(v));
            }
          }
          return next;
        },
        { replace: opts?.replace ?? false },
      );
    },
    [setSearchParams],
  );
}
