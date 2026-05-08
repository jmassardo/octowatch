import { useCallback, useEffect, useMemo, useState } from 'react';

const RECENT_SEARCH_STORAGE_KEY = 'octowatch-command-palette-recent-searches';
const MAX_RECENT_SEARCHES = 10;

function parseRecentSearches(rawValue: string | null): string[] {
  if (!rawValue) return [];

  try {
    const parsed = JSON.parse(rawValue);
    if (!Array.isArray(parsed)) return [];

    return parsed.filter((entry): entry is string => typeof entry === 'string').slice(0, MAX_RECENT_SEARCHES);
  } catch {
    return [];
  }
}

export function loadRecentCommandPaletteSearches(): string[] {
  if (typeof window === 'undefined') return [];
  return parseRecentSearches(window.localStorage.getItem(RECENT_SEARCH_STORAGE_KEY));
}

export function saveRecentCommandPaletteSearch(query: string): string[] {
  if (typeof window === 'undefined') return [];

  const trimmedQuery = query.trim();
  if (!trimmedQuery) return loadRecentCommandPaletteSearches();

  const recent = loadRecentCommandPaletteSearches().filter(
    (entry) => entry.toLowerCase() !== trimmedQuery.toLowerCase(),
  );
  const next = [trimmedQuery, ...recent].slice(0, MAX_RECENT_SEARCHES);
  window.localStorage.setItem(RECENT_SEARCH_STORAGE_KEY, JSON.stringify(next));
  return next;
}

export function useCommandPalette() {
  const [isOpen, setIsOpen] = useState(false);

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);
  const toggle = useCallback(() => setIsOpen((currentValue) => !currentValue), []);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setIsOpen((currentValue) => !currentValue);
      }

      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return useMemo(
    () => ({ isOpen, open, close, toggle }),
    [close, isOpen, open, toggle],
  );
}
