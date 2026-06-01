import { useEffect, useRef, useCallback } from 'react';

const SESSION_TIMEOUT_KEY = 'octowatch-session-timeout-ms';
const RETURN_URL_KEY = 'octowatch-return-url';
const DEFAULT_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes
const ACTIVITY_THROTTLE_MS = 30_000; // Only reset timer every 30s at most

/**
 * Returns the configured session timeout in milliseconds.
 * Reads from localStorage (set via settings), falling back to env var or default.
 */
function getTimeoutMs(): number {
  const stored = localStorage.getItem(SESSION_TIMEOUT_KEY);
  if (stored) {
    const parsed = parseInt(stored, 10);
    if (!isNaN(parsed) && parsed > 0) return parsed;
  }
  const envVal = import.meta.env.VITE_SESSION_TIMEOUT_MS;
  if (envVal) {
    const parsed = parseInt(envVal, 10);
    if (!isNaN(parsed) && parsed > 0) return parsed;
  }
  return DEFAULT_TIMEOUT_MS;
}

/**
 * Saves the current route to localStorage so the user can be redirected
 * back after re-authentication.
 */
export function saveCurrentRoute(): void {
  const path = window.location.pathname + window.location.search;
  // Don't save login/setup routes
  if (path === '/login' || path === '/setup' || path === '/') return;
  localStorage.setItem(RETURN_URL_KEY, path);
}

/**
 * Retrieves and clears the saved return URL from localStorage.
 */
export function consumeReturnUrl(): string | null {
  const url = localStorage.getItem(RETURN_URL_KEY);
  if (url) {
    localStorage.removeItem(RETURN_URL_KEY);
  }
  return url;
}

/**
 * Activity-aware session timeout hook.
 * Resets the inactivity timer on meaningful user interactions (clicks, keydown,
 * pointer movement, and navigation/API calls via a custom event).
 * On timeout, saves the current route and redirects to /login.
 */
export function useSessionTimeout(): void {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastActivityRef = useRef<number>(0);

  const handleExpiry = useCallback(() => {
    saveCurrentRoute();
    window.location.replace('/login');
  }, []);

  const resetTimer = useCallback(() => {
    const now = Date.now();
    // Throttle: only reset if enough time has passed since last reset
    if (now - lastActivityRef.current < ACTIVITY_THROTTLE_MS) return;
    lastActivityRef.current = now;

    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(handleExpiry, getTimeoutMs());
  }, [handleExpiry]);

  // Force-reset without throttle (used for initial setup and API activity event)
  const forceReset = useCallback(() => {
    lastActivityRef.current = Date.now();
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
    }
    timerRef.current = setTimeout(handleExpiry, getTimeoutMs());
  }, [handleExpiry]);

  useEffect(() => {
    // Start the timer immediately
    forceReset();

    const onActivity = () => resetTimer();
    const onApiActivity = () => forceReset();

    // Listen to meaningful user activity
    window.addEventListener('click', onActivity);
    window.addEventListener('keydown', onActivity);
    window.addEventListener('pointermove', onActivity);
    window.addEventListener('scroll', onActivity, { passive: true });

    // Custom event dispatched by the API client on successful requests
    window.addEventListener('octowatch:api-activity', onApiActivity);

    return () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current);
      }
      window.removeEventListener('click', onActivity);
      window.removeEventListener('keydown', onActivity);
      window.removeEventListener('pointermove', onActivity);
      window.removeEventListener('scroll', onActivity);
      window.removeEventListener('octowatch:api-activity', onApiActivity);
    };
  }, [resetTimer, forceReset]);
}
