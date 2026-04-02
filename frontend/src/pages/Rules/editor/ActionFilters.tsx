import { useState, useCallback } from 'react';
import type { KeyboardEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getSuggestedActions } from '../../../api/suggestions';
import { Autocomplete } from '../../../components/primitives/Autocomplete';
import styles from './LogicConfigEditor.module.css';

interface ActionFiltersProps {
  actions: string[];
  onChange: (actions: string[]) => void;
}

export function ActionFilters({ actions, onChange }: ActionFiltersProps) {
  const [inputValue, setInputValue] = useState('');

  const { data: suggestionsData } = useQuery({
    queryKey: ['suggestions', 'actions'],
    queryFn: getSuggestedActions,
    staleTime: 5 * 60 * 1000,
  });

  const allSuggestions = suggestionsData?.actions ?? [];

  // Filter out actions that are already selected
  const availableSuggestions = allSuggestions.filter((s) => !actions.includes(s));

  const addAction = useCallback(
    (raw: string) => {
      const value = raw.trim();
      if (value === '' || actions.includes(value)) {
        return;
      }
      onChange([...actions, value]);
    },
    [actions, onChange],
  );

  const removeAction = useCallback(
    (index: number) => {
      onChange(actions.filter((_, i) => i !== index));
    },
    [actions, onChange],
  );

  const handleCommit = useCallback(
    (value: string) => {
      addAction(value);
      setInputValue('');
    },
    [addAction],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === ',') {
        e.preventDefault();
        addAction(inputValue);
        setInputValue('');
      }
      if (e.key === 'Backspace' && inputValue === '' && actions.length > 0) {
        removeAction(actions.length - 1);
      }
    },
    [inputValue, actions, addAction, removeAction],
  );

  const handleChange = useCallback(
    (value: string) => {
      if (value.includes(',')) {
        const parts = value.split(',');
        for (const part of parts.slice(0, -1)) {
          const trimmed = part.trim();
          if (trimmed) {
            addAction(trimmed);
          }
        }
        setInputValue(parts[parts.length - 1] ?? '');
      } else {
        setInputValue(value);
      }
    },
    [addAction],
  );

  return (
    <div
      className={styles.chipContainer}
      role="group"
      aria-label="Action filters"
      onKeyDown={handleKeyDown}
    >
      {actions.map((action, index) => (
        <span key={`${action}-${index}`} className={styles.chip}>
          <span className={styles.chipText}>{action}</span>
          <button
            type="button"
            className={styles.chipRemove}
            onClick={() => removeAction(index)}
            aria-label={`Remove action ${action}`}
          >
            ×
          </button>
        </span>
      ))}
      <Autocomplete
        value={inputValue}
        onChange={handleChange}
        suggestions={availableSuggestions}
        onCommit={handleCommit}
        placeholder={actions.length === 0 ? 'e.g., git.clone' : ''}
        className={styles.chipInput}
        ariaLabel="Add action filter"
      />
    </div>
  );
}
