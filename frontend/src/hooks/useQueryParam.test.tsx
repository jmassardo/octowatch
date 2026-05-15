import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import {
  useQueryParam,
  useQueryParamInt,
  useEnumQueryParam,
  useSetQueryParams,
} from './useQueryParam';

function wrapper(initialEntries: string[] = ['/']) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <MemoryRouter initialEntries={initialEntries} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>{children}</MemoryRouter>;
  };
}

describe('useQueryParam', () => {
  it('returns default value when param is absent', () => {
    const { result } = renderHook(() => useQueryParam('tab', 'overview'), {
      wrapper: wrapper(),
    });
    expect(result.current[0]).toBe('overview');
  });

  it('reads value from URL', () => {
    const { result } = renderHook(() => useQueryParam('tab', 'overview'), {
      wrapper: wrapper(['/?tab=secrets']),
    });
    expect(result.current[0]).toBe('secrets');
  });

  it('updates value and reflects in hook', () => {
    const { result } = renderHook(() => useQueryParam('tab', 'overview'), {
      wrapper: wrapper(),
    });

    act(() => {
      result.current[1]('code');
    });

    expect(result.current[0]).toBe('code');
  });

  it('removes param from URL when set to default', () => {
    const { result } = renderHook(() => useQueryParam('tab', 'overview'), {
      wrapper: wrapper(['/?tab=secrets']),
    });

    act(() => {
      result.current[1]('overview');
    });

    expect(result.current[0]).toBe('overview');
  });

  it('preserves other params when updating', () => {
    const { result } = renderHook(
      () => ({
        tab: useQueryParam('tab', 'overview'),
        page: useQueryParam('page', '1'),
      }),
      { wrapper: wrapper(['/?tab=secrets&page=3']) },
    );

    act(() => {
      result.current.tab[1]('code');
    });

    expect(result.current.tab[0]).toBe('code');
    expect(result.current.page[0]).toBe('3');
  });
});

describe('useQueryParamInt', () => {
  it('returns default for absent param', () => {
    const { result } = renderHook(() => useQueryParamInt('page', 1), {
      wrapper: wrapper(),
    });
    expect(result.current[0]).toBe(1);
  });

  it('parses numeric value from URL', () => {
    const { result } = renderHook(() => useQueryParamInt('page', 1), {
      wrapper: wrapper(['/?page=5']),
    });
    expect(result.current[0]).toBe(5);
  });

  it('returns default for invalid numeric value', () => {
    const { result } = renderHook(() => useQueryParamInt('page', 1), {
      wrapper: wrapper(['/?page=abc']),
    });
    expect(result.current[0]).toBe(1);
  });

  it('returns default for negative value', () => {
    const { result } = renderHook(() => useQueryParamInt('page', 1), {
      wrapper: wrapper(['/?page=-3']),
    });
    expect(result.current[0]).toBe(1);
  });
});

describe('useEnumQueryParam', () => {
  const validValues = ['open', 'closed', 'all'] as const;

  it('returns default for absent param', () => {
    const { result } = renderHook(() => useEnumQueryParam('status', validValues, 'open'), {
      wrapper: wrapper(),
    });
    expect(result.current[0]).toBe('open');
  });

  it('returns valid value from URL', () => {
    const { result } = renderHook(() => useEnumQueryParam('status', validValues, 'open'), {
      wrapper: wrapper(['/?status=closed']),
    });
    expect(result.current[0]).toBe('closed');
  });

  it('returns default for invalid URL value', () => {
    const { result } = renderHook(() => useEnumQueryParam('status', validValues, 'open'), {
      wrapper: wrapper(['/?status=invalid']),
    });
    expect(result.current[0]).toBe('open');
  });
});

describe('useSetQueryParams', () => {
  it('sets multiple params atomically', () => {
    const { result } = renderHook(
      () => ({
        setter: useSetQueryParams(),
        tab: useQueryParam('tab', 'overview'),
        page: useQueryParamInt('page', 1),
      }),
      { wrapper: wrapper() },
    );

    act(() => {
      result.current.setter({ tab: 'secrets', page: 3 });
    });

    expect(result.current.tab[0]).toBe('secrets');
    expect(result.current.page[0]).toBe(3);
  });

  it('removes params when set to null', () => {
    const { result } = renderHook(
      () => ({
        setter: useSetQueryParams(),
        tab: useQueryParam('tab', 'overview'),
        page: useQueryParamInt('page', 1),
      }),
      { wrapper: wrapper(['/?tab=secrets&page=3']) },
    );

    act(() => {
      result.current.setter({ tab: null, page: null });
    });

    expect(result.current.tab[0]).toBe('overview');
    expect(result.current.page[0]).toBe(1);
  });
});
