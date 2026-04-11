import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useTheme } from './useTheme';

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  it('defaults to system when no localStorage value', () => {
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('system');
  });

  it('reads initial theme from localStorage', () => {
    localStorage.setItem('octowatch-theme', 'dark');
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe('dark');
  });

  it('sets data-theme attribute on document when dark', () => {
    localStorage.setItem('octowatch-theme', 'dark');
    renderHook(() => useTheme());
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('sets data-theme attribute on document when light', () => {
    localStorage.setItem('octowatch-theme', 'light');
    renderHook(() => useTheme());
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('removes data-theme when system', () => {
    document.documentElement.setAttribute('data-theme', 'dark');
    const { result } = renderHook(() => useTheme());
    act(() => {
      result.current.setTheme('system');
    });
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('toggleTheme cycles through light → dark → system', () => {
    localStorage.setItem('octowatch-theme', 'light');
    const { result } = renderHook(() => useTheme());

    expect(result.current.theme).toBe('light');

    act(() => {
      result.current.toggleTheme();
    });
    expect(result.current.theme).toBe('dark');

    act(() => {
      result.current.toggleTheme();
    });
    expect(result.current.theme).toBe('system');

    act(() => {
      result.current.toggleTheme();
    });
    expect(result.current.theme).toBe('light');
  });

  it('persists theme to localStorage', () => {
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme('dark');
    });
    expect(localStorage.getItem('octowatch-theme')).toBe('dark');

    act(() => {
      result.current.setTheme('light');
    });
    expect(localStorage.getItem('octowatch-theme')).toBe('light');
  });

  it('removes localStorage entry when set to system', () => {
    localStorage.setItem('octowatch-theme', 'dark');
    const { result } = renderHook(() => useTheme());

    act(() => {
      result.current.setTheme('system');
    });
    expect(localStorage.getItem('octowatch-theme')).toBeNull();
  });
});
