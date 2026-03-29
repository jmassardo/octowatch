import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent, ChangeEvent } from 'react';
import styles from './Autocomplete.module.css';

/** Maximum number of suggestions shown in the dropdown. */
const MAX_VISIBLE = 8;

interface AutocompleteProps {
  /** Current input value (controlled). */
  value: string;
  /** Called on every keystroke or programmatic value change. */
  onChange: (value: string) => void;
  /** Full list of possible suggestions (unfiltered). */
  suggestions: string[];
  /** Input placeholder text. */
  placeholder?: string;
  /** Called when a value is committed (Enter, Tab, or click on suggestion). */
  onCommit?: (value: string) => void;
  /** Additional class name applied to the inner input element. */
  className?: string;
  /** Accessible label for the input. */
  ariaLabel?: string;
}

/**
 * Filter suggestions by matching the query as either a prefix or a substring
 * (case-insensitive). Prefix matches are sorted first.
 */
function filterSuggestions(query: string, suggestions: string[]): string[] {
  if (!query) return [];
  const lower = query.toLowerCase();

  const prefixMatches: string[] = [];
  const substringMatches: string[] = [];

  for (const s of suggestions) {
    const sLower = s.toLowerCase();
    if (sLower.startsWith(lower)) {
      prefixMatches.push(s);
    } else if (sLower.includes(lower)) {
      substringMatches.push(s);
    }
  }

  return [...prefixMatches, ...substringMatches].slice(0, MAX_VISIBLE);
}

/**
 * Render a suggestion string with the matching portion highlighted in bold.
 */
function HighlightedText({ text, query }: { text: string; query: string }) {
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

export function Autocomplete({
  value,
  onChange,
  suggestions,
  placeholder,
  onCommit,
  className,
  ariaLabel,
}: AutocompleteProps) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(
    () => filterSuggestions(value, suggestions),
    [value, suggestions],
  );

  // Clamp activeIndex within bounds whenever the filtered list changes.
  // This is derived state, not an effect — we compute the clamped value
  // inline so React never sees a stale activeIndex.
  const clampedActiveIndex = activeIndex >= filtered.length ? -1 : activeIndex;

  // Close dropdown on outside click
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
      onChange(suggestion);
      setOpen(false);
      setActiveIndex(-1);
      onCommit?.(suggestion);
    },
    [onChange, onCommit],
  );

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      onChange(e.target.value);
      setOpen(true);
      setActiveIndex(-1);
    },
    [onChange],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (!open || filtered.length === 0) {
        if (e.key === 'Enter') {
          if (value.trim()) {
            onCommit?.(value.trim());
          }
        }
        return;
      }

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setActiveIndex((prev) => (prev < filtered.length - 1 ? prev + 1 : 0));
          break;

        case 'ArrowUp':
          e.preventDefault();
          setActiveIndex((prev) => (prev > 0 ? prev - 1 : filtered.length - 1));
          break;

        case 'Enter':
          e.preventDefault();
          if (activeIndex >= 0 && activeIndex < filtered.length) {
            selectSuggestion(filtered[activeIndex]);
          } else if (value.trim()) {
            onCommit?.(value.trim());
            setOpen(false);
          }
          break;

        case 'Tab':
          if (activeIndex >= 0 && activeIndex < filtered.length) {
            e.preventDefault();
            selectSuggestion(filtered[activeIndex]);
          }
          break;

        case 'Escape':
          e.preventDefault();
          setOpen(false);
          setActiveIndex(-1);
          break;
      }
    },
    [open, filtered, activeIndex, value, onCommit, selectSuggestion],
  );

  // Scroll the active option into view
  useEffect(() => {
    if (clampedActiveIndex >= 0 && listRef.current) {
      const items = listRef.current.querySelectorAll('[data-option]');
      items[clampedActiveIndex]?.scrollIntoView({ block: 'nearest' });
    }
  }, [clampedActiveIndex]);

  const showDropdown = open && filtered.length > 0 && value.length > 0;

  const inputCls = [styles.input, className].filter(Boolean).join(' ');

  return (
    <div className={styles.wrapper} ref={wrapperRef}>
      <input
        type="text"
        className={inputCls}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onFocus={() => {
          if (value && filtered.length > 0) setOpen(true);
        }}
        placeholder={placeholder}
        aria-label={ariaLabel}
        role="combobox"
        aria-expanded={showDropdown}
        aria-autocomplete="list"
        aria-activedescendant={
          clampedActiveIndex >= 0 ? `autocomplete-option-${clampedActiveIndex}` : undefined
        }
        autoComplete="off"
      />
      {showDropdown && (
        <div
          className={styles.dropdown}
          ref={listRef}
          role="listbox"
        >
          {filtered.map((suggestion, index) => {
            const isActive = index === clampedActiveIndex;
            const cls = [styles.option, isActive && styles.optionActive]
              .filter(Boolean)
              .join(' ');

            return (
              <div
                key={suggestion}
                id={`autocomplete-option-${index}`}
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
                <HighlightedText text={suggestion} query={value} />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
