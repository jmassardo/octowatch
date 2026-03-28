import { useState, useCallback } from 'react';
import type { KeyboardEvent, ChangeEvent } from 'react';
import styles from './LogicConfigEditor.module.css';

interface ActionFiltersProps {
  actions: string[];
  onChange: (actions: string[]) => void;
}

export function ActionFilters({ actions, onChange }: ActionFiltersProps) {
  const [inputValue, setInputValue] = useState('');

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

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' || e.key === ',') {
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

  const handleChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    if (val.includes(',')) {
      const parts = val.split(',');
      for (const part of parts.slice(0, -1)) {
        const trimmed = part.trim();
        if (trimmed) {
          addAction(trimmed);
        }
      }
      setInputValue(parts[parts.length - 1] ?? '');
    } else {
      setInputValue(val);
    }
  }, [addAction]);

  return (
    <div className={styles.chipContainer} role="group" aria-label="Action filters">
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
      <input
        type="text"
        className={styles.chipInput}
        value={inputValue}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={actions.length === 0 ? 'e.g., git.clone' : ''}
        aria-label="Add action filter"
      />
    </div>
  );
}
