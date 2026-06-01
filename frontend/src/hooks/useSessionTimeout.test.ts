import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSessionTimeout, saveCurrentRoute, consumeReturnUrl } from './useSessionTimeout';

describe('useSessionTimeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
    // Mock window.location.replace
    Object.defineProperty(window, 'location', {
      value: { ...window.location, replace: vi.fn(), pathname: '/events', search: '?page=2' },
      writable: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('redirects to /login after timeout with default 30 minutes', () => {
    renderHook(() => useSessionTimeout());

    // Advance to just before timeout — should not redirect
    act(() => {
      vi.advanceTimersByTime(30 * 60 * 1000 - 1000);
    });
    expect(window.location.replace).not.toHaveBeenCalled();

    // Advance past timeout
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(window.location.replace).toHaveBeenCalledWith('/login');
  });

  it('saves current route to localStorage on expiry', () => {
    renderHook(() => useSessionTimeout());

    act(() => {
      vi.advanceTimersByTime(30 * 60 * 1000 + 1);
    });

    expect(localStorage.getItem('octowatch-return-url')).toBe('/events?page=2');
  });

  it('resets timer on click events (respecting throttle)', () => {
    renderHook(() => useSessionTimeout());

    // Advance 29 minutes
    act(() => {
      vi.advanceTimersByTime(29 * 60 * 1000);
    });

    // Advance past throttle window (30s) and trigger click
    act(() => {
      vi.advanceTimersByTime(31_000);
      window.dispatchEvent(new MouseEvent('click'));
    });

    // After the click, timer should be reset. Advance another 29 minutes — no redirect
    act(() => {
      vi.advanceTimersByTime(29 * 60 * 1000);
    });
    expect(window.location.replace).not.toHaveBeenCalled();

    // But 31 more minutes should trigger it
    act(() => {
      vi.advanceTimersByTime(2 * 60 * 1000);
    });
    expect(window.location.replace).toHaveBeenCalledWith('/login');
  });

  it('resets timer on API activity custom event (bypasses throttle)', () => {
    renderHook(() => useSessionTimeout());

    // Advance 29 minutes
    act(() => {
      vi.advanceTimersByTime(29 * 60 * 1000);
    });

    // API activity event always resets (no throttle)
    act(() => {
      window.dispatchEvent(new CustomEvent('octowatch:api-activity'));
    });

    // Advance another 29 minutes — no redirect yet
    act(() => {
      vi.advanceTimersByTime(29 * 60 * 1000);
    });
    expect(window.location.replace).not.toHaveBeenCalled();
  });

  it('respects custom timeout from localStorage', () => {
    localStorage.setItem('octowatch-session-timeout-ms', '60000'); // 1 minute
    renderHook(() => useSessionTimeout());

    act(() => {
      vi.advanceTimersByTime(59_000);
    });
    expect(window.location.replace).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(window.location.replace).toHaveBeenCalledWith('/login');
  });

  it('cleans up on unmount', () => {
    const { unmount } = renderHook(() => useSessionTimeout());
    unmount();

    // After unmount, timer should be cleared — no redirect even after timeout
    act(() => {
      vi.advanceTimersByTime(60 * 60 * 1000);
    });
    expect(window.location.replace).not.toHaveBeenCalled();
  });
});

describe('saveCurrentRoute', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('saves pathname + search to localStorage', () => {
    Object.defineProperty(window, 'location', {
      value: { pathname: '/threats', search: '?severity=high' },
      writable: true,
    });
    saveCurrentRoute();
    expect(localStorage.getItem('octowatch-return-url')).toBe('/threats?severity=high');
  });

  it('does not save /login path', () => {
    Object.defineProperty(window, 'location', {
      value: { pathname: '/login', search: '' },
      writable: true,
    });
    saveCurrentRoute();
    expect(localStorage.getItem('octowatch-return-url')).toBeNull();
  });

  it('does not save /setup path', () => {
    Object.defineProperty(window, 'location', {
      value: { pathname: '/setup', search: '' },
      writable: true,
    });
    saveCurrentRoute();
    expect(localStorage.getItem('octowatch-return-url')).toBeNull();
  });

  it('does not save root path', () => {
    Object.defineProperty(window, 'location', {
      value: { pathname: '/', search: '' },
      writable: true,
    });
    saveCurrentRoute();
    expect(localStorage.getItem('octowatch-return-url')).toBeNull();
  });
});

describe('consumeReturnUrl', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('returns saved URL and removes it from localStorage', () => {
    localStorage.setItem('octowatch-return-url', '/events?page=3');
    const url = consumeReturnUrl();
    expect(url).toBe('/events?page=3');
    expect(localStorage.getItem('octowatch-return-url')).toBeNull();
  });

  it('returns null when no saved URL exists', () => {
    const url = consumeReturnUrl();
    expect(url).toBeNull();
  });
});
