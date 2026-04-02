import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import styles from './EventSearchInput.module.css';

/** Maximum number of suggestions shown in the dropdown. */
const MAX_VISIBLE = 8;

/** Filter key suggestions offered when the user hasn't started a key:value pair. */
const FILTER_KEYS = ['action:', 'actor:', 'repo:', 'org:', 'since:', 'until:'];

interface EventSearchInputProps {
  /** Current search text (controlled). */
  value: string;
  /** Called on every keystroke. */
  onChange: (value: string) => void;
  /** Called when the user presses Enter to commit the search. */
  onSubmit: (value: string) => void;
  /** Distinct action values for autocomplete. */
  actionSuggestions: string[];
  /** Distinct actor values for autocomplete. */
  actorSuggestions: string[];
  /** Placeholder for the input. */
  placeholder?: string;
  /** HTML id for the input element (allows external focusing). */
  id?: string;
}

interface ParsedContext {
  /** The prefix key (e.g. "action", "actor") or null for filter key suggestions. */
  prefix: string | null;
  /** The partial value typed after the colon, used for filtering. */
  query: string;
  /** Start index of the current token in the full input string. */
  tokenStart: number;
  /** End index of the current token in the full input string. */
  tokenEnd: number;
}

/**
 * Parse what the user is currently typing based on cursor position.
 * Returns the context needed to show appropriate suggestions.
 */
function parseContext(value: string, cursorPos: number): ParsedContext {
  // Find the boundaries of the current token (space-delimited)
  let tokenStart = cursorPos;
  while (tokenStart > 0 && value[tokenStart - 1] !== ' ') {
    tokenStart--;
  }
  const tokenEnd = cursorPos;
  const token = value.slice(tokenStart, tokenEnd);

  // Check if the token contains a colon (key:value pattern)
  const colonIdx = token.indexOf(':');
  if (colonIdx >= 0) {
    const prefix = token.slice(0, colonIdx);
    const query = token.slice(colonIdx + 1);
    return { prefix, query, tokenStart, tokenEnd };
  }

  // No colon – show filter key suggestions
  return { prefix: null, query: token, tokenStart, tokenEnd };
}

/**
 * Filter items by case-insensitive prefix and substring match.
 * Prefix matches come first.
 */
function filterItems(query: string, items: string[]): string[] {
  if (!query) return items.slice(0, MAX_VISIBLE);
  const lower = query.toLowerCase();

  const prefixMatches: string[] = [];
  const substringMatches: string[] = [];

  for (const item of items) {
    const itemLower = item.toLowerCase();
    if (itemLower.startsWith(lower)) {
      prefixMatches.push(item);
    } else if (itemLower.includes(lower)) {
      substringMatches.push(item);
    }
  }

  return [...prefixMatches, ...substringMatches].slice(0, MAX_VISIBLE);
}

/**
 * Render text with the matching portion highlighted in bold.
 */
function HighlightedOption({ text, query }: { text: string; query: string }) {
  if (!query) return <>{text}</>;

  const lower = text.toLowerCase();
  const qLower = query.toLowerCase();
  const idx = lower.indexOf(qLower);

  if (idx === -1) return <>{text}</>;

  const before = text.slice(0, idx);
  const match = text.slice(idx, idx + query.length);
  const after = text.slice(idx + query.length);

  return (
    <>
      {before}
      <span className={styles.highlight}>{match}</span>
      {after}
    </>
  );
}

export function EventSearchInput({
  value,
  onChange,
  onSubmit,
  actionSuggestions,
  actorSuggestions,
  placeholder,
  id,
}: EventSearchInputProps) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [cursorPos, setCursorPos] = useState(0);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const internalRef = useRef<HTMLInputElement>(null);

  // Compute context and suggestions based on tracked cursor position
  const context = useMemo(() => parseContext(value, cursorPos), [value, cursorPos]);

  const suggestions = useMemo(() => {
    if (context.prefix === null) {
      // Show filter key suggestions filtered by what's typed
      return filterItems(context.query, FILTER_KEYS);
    }
    if (context.prefix === 'action') {
      return filterItems(context.query, actionSuggestions);
    }
    if (context.prefix === 'actor') {
      return filterItems(context.query, actorSuggestions);
    }
    return [];
  }, [context, actionSuggestions, actorSuggestions]);

  // Clamp activeIndex within bounds (derived state, no effect needed)
  const clampedActiveIndex = activeIndex >= suggestions.length ? -1 : activeIndex;

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
        setActiveIndex(-1);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const selectSuggestion = useCallback(
    (suggestion: string) => {
      // Replace the current token with the selected suggestion
      const before = value.slice(0, context.tokenStart);
      const after = value.slice(context.tokenEnd);

      let replacement: string;
      if (context.prefix === null) {
        // Selecting a filter key like "action:" – insert it
        replacement = suggestion;
      } else {
        // Selecting a value – reconstruct key:value
        replacement = `${context.prefix}:${suggestion}`;
      }

      const newValue = before + replacement + (after.startsWith(' ') ? after : ' ' + after);
      onChange(newValue.trimEnd() + (context.prefix !== null ? ' ' : ''));
      setOpen(false);
      setActiveIndex(-1);

      // Refocus input
      requestAnimationFrame(() => {
        internalRef.current?.focus();
      });
    },
    [value, context, onChange],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (!open || suggestions.length === 0) {
        if (e.key === 'Enter' && value.trim()) {
          e.preventDefault();
          onSubmit(value.trim());
        }
        return;
      }

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setActiveIndex((prev) => (prev < suggestions.length - 1 ? prev + 1 : 0));
          break;

        case 'ArrowUp':
          e.preventDefault();
          setActiveIndex((prev) => (prev > 0 ? prev - 1 : suggestions.length - 1));
          break;

        case 'Enter':
          e.preventDefault();
          if (activeIndex >= 0 && activeIndex < suggestions.length) {
            selectSuggestion(suggestions[activeIndex]);
          } else if (value.trim()) {
            onSubmit(value.trim());
            setOpen(false);
          }
          break;

        case 'Tab':
          if (activeIndex >= 0 && activeIndex < suggestions.length) {
            e.preventDefault();
            selectSuggestion(suggestions[activeIndex]);
          }
          break;

        case 'Escape':
          e.preventDefault();
          setOpen(false);
          setActiveIndex(-1);
          break;
      }
    },
    [open, suggestions, activeIndex, value, onSubmit, selectSuggestion],
  );

  // Scroll active option into view
  useEffect(() => {
    if (clampedActiveIndex >= 0 && listRef.current) {
      const items = listRef.current.querySelectorAll('[data-option]');
      items[clampedActiveIndex]?.scrollIntoView({ block: 'nearest' });
    }
  }, [clampedActiveIndex]);

  const showDropdown = open && suggestions.length > 0;

  // Determine section label
  const sectionLabel =
    context.prefix === null
      ? 'Filter by'
      : context.prefix === 'action'
        ? 'Actions'
        : context.prefix === 'actor'
          ? 'Actors'
          : null;

  return (
    <div className={styles.wrapper} ref={wrapperRef}>
      <input
        ref={internalRef}
        id={id}
        type="text"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setCursorPos(e.target.selectionStart ?? e.target.value.length);
          setOpen(true);
          setActiveIndex(-1);
        }}
        onKeyDown={handleKeyDown}
        onFocus={() => {
          if (suggestions.length > 0) setOpen(true);
        }}
        onClick={(e) => {
          setCursorPos((e.target as HTMLInputElement).selectionStart ?? value.length);
        }}
        placeholder={placeholder}
        role="combobox"
        aria-expanded={showDropdown}
        aria-autocomplete="list"
        aria-activedescendant={
          clampedActiveIndex >= 0 ? `search-option-${clampedActiveIndex}` : undefined
        }
        autoComplete="off"
      />
      {showDropdown && (
        <div className={styles.dropdown} ref={listRef} role="listbox">
          {sectionLabel && <div className={styles.sectionLabel}>{sectionLabel}</div>}
          {suggestions.map((suggestion, index) => {
            const isActive = index === clampedActiveIndex;
            const cls = [styles.option, isActive && styles.optionActive].filter(Boolean).join(' ');

            return (
              <div
                key={suggestion}
                id={`search-option-${index}`}
                className={cls}
                role="option"
                aria-selected={isActive}
                data-option=""
                onMouseDown={(e) => {
                  e.preventDefault();
                  selectSuggestion(suggestion);
                }}
                onMouseEnter={() => setActiveIndex(index)}
              >
                <HighlightedOption text={suggestion} query={context.query} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
