import { useCallback } from 'react';
import type { ChangeEvent } from 'react';
import type { FieldCondition } from './types';
import styles from './LogicConfigEditor.module.css';

const OPERATORS = [
  { value: 'eq', label: 'equals' },
  { value: 'ne', label: 'not equals' },
  { value: 'gt', label: 'greater than' },
  { value: 'gte', label: 'greater or equal' },
  { value: 'lt', label: 'less than' },
  { value: 'lte', label: 'less or equal' },
  { value: 'in', label: 'in' },
  { value: 'not_in', label: 'not in' },
  { value: 'contains', label: 'contains' },
  { value: 'not_contains', label: 'not contains' },
  { value: 'exists', label: 'exists' },
  { value: 'not_exists', label: 'not exists' },
  { value: 'matches_glob', label: 'matches glob' },
  { value: 'scope_contains', label: 'scope contains' },
] as const;

const HIDE_VALUE_OPERATORS = new Set(['exists', 'not_exists']);
const MULTI_VALUE_OPERATORS = new Set(['in', 'not_in']);

interface FieldConditionsProps {
  conditions: FieldCondition[];
  onChange: (conditions: FieldCondition[]) => void;
}

export function FieldConditions({ conditions, onChange }: FieldConditionsProps) {
  const updateCondition = useCallback(
    (index: number, patch: Partial<FieldCondition>) => {
      const updated = conditions.map((cond, i) => {
        if (i !== index) return cond;
        const merged = { ...cond, ...patch };
        if (HIDE_VALUE_OPERATORS.has(merged.operator)) {
          merged.value = undefined;
        }
        return merged;
      });
      onChange(updated);
    },
    [conditions, onChange],
  );

  const addCondition = useCallback(() => {
    onChange([...conditions, { field: '', operator: 'eq', value: '' }]);
  }, [conditions, onChange]);

  const removeCondition = useCallback(
    (index: number) => {
      onChange(conditions.filter((_, i) => i !== index));
    },
    [conditions, onChange],
  );

  const handleFieldChange = useCallback(
    (index: number, e: ChangeEvent<HTMLInputElement>) => {
      updateCondition(index, { field: e.target.value });
    },
    [updateCondition],
  );

  const handleOperatorChange = useCallback(
    (index: number, e: ChangeEvent<HTMLSelectElement>) => {
      updateCondition(index, { operator: e.target.value });
    },
    [updateCondition],
  );

  const handleValueChange = useCallback(
    (index: number, e: ChangeEvent<HTMLInputElement>) => {
      const op = conditions[index]?.operator ?? 'eq';
      const raw = e.target.value;
      if (MULTI_VALUE_OPERATORS.has(op)) {
        updateCondition(index, { value: raw });
      } else {
        updateCondition(index, { value: raw });
      }
    },
    [conditions, updateCondition],
  );

  return (
    <div className={styles.conditionsContainer} role="group" aria-label="Field conditions">
      {conditions.map((cond, index) => {
        const hideValue = HIDE_VALUE_OPERATORS.has(cond.operator);
        const isMultiValue = MULTI_VALUE_OPERATORS.has(cond.operator);

        return (
          <div key={index} className={styles.conditionRow}>
            <input
              type="text"
              className={styles.conditionField}
              value={cond.field}
              onChange={(e) => handleFieldChange(index, e)}
              placeholder="e.g., data.scope"
              aria-label={`Condition ${index + 1} field`}
            />
            <select
              className={styles.conditionOperator}
              value={cond.operator}
              onChange={(e) => handleOperatorChange(index, e)}
              aria-label={`Condition ${index + 1} operator`}
            >
              {OPERATORS.map((op) => (
                <option key={op.value} value={op.value}>
                  {op.label}
                </option>
              ))}
            </select>
            {!hideValue && (
              <input
                type="text"
                className={styles.conditionValue}
                value={typeof cond.value === 'string' ? cond.value : String(cond.value ?? '')}
                onChange={(e) => handleValueChange(index, e)}
                placeholder={isMultiValue ? 'comma-separated values' : 'value'}
                aria-label={`Condition ${index + 1} value`}
              />
            )}
            <button
              type="button"
              className={styles.removeBtn}
              onClick={() => removeCondition(index)}
              aria-label={`Remove condition ${index + 1}`}
            >
              ×
            </button>
          </div>
        );
      })}
      <button type="button" className={styles.addBtn} onClick={addCondition}>
        + Add condition
      </button>
    </div>
  );
}
