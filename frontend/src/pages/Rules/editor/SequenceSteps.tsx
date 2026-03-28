import { useCallback } from 'react';
import type { ChangeEvent } from 'react';
import type { SequenceStep } from './types';
import styles from './LogicConfigEditor.module.css';

interface SequenceStepsProps {
  steps: SequenceStep[];
  onChange: (steps: SequenceStep[]) => void;
}

export function SequenceSteps({ steps, onChange }: SequenceStepsProps) {
  const updateStep = useCallback(
    (index: number, patch: Partial<SequenceStep>) => {
      onChange(steps.map((step, i) => (i === index ? { ...step, ...patch } : step)));
    },
    [steps, onChange],
  );

  const addStep = useCallback(() => {
    onChange([...steps, { action: '', min_count: 1 }]);
  }, [steps, onChange]);

  const removeStep = useCallback(
    (index: number) => {
      onChange(steps.filter((_, i) => i !== index));
    },
    [steps, onChange],
  );

  const moveStep = useCallback(
    (index: number, direction: -1 | 1) => {
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= steps.length) return;
      const updated = [...steps];
      const temp = updated[targetIndex]!;
      updated[targetIndex] = updated[index]!;
      updated[index] = temp;
      onChange(updated);
    },
    [steps, onChange],
  );

  const handleActionChange = useCallback(
    (index: number, e: ChangeEvent<HTMLInputElement>) => {
      updateStep(index, { action: e.target.value });
    },
    [updateStep],
  );

  const handleMinCountChange = useCallback(
    (index: number, e: ChangeEvent<HTMLInputElement>) => {
      const parsed = parseInt(e.target.value, 10);
      updateStep(index, { min_count: Number.isNaN(parsed) ? 1 : Math.max(1, parsed) });
    },
    [updateStep],
  );

  return (
    <div className={styles.stepsContainer} role="list" aria-label="Sequence steps">
      {steps.map((step, index) => (
        <div key={index} className={styles.stepRow} role="listitem">
          <span className={styles.stepBadge} aria-label={`Step ${index + 1}`}>
            {index + 1}
          </span>
          <div className={styles.stepFields}>
            <input
              type="text"
              className={styles.stepActionInput}
              value={step.action}
              onChange={(e) => handleActionChange(index, e)}
              placeholder="e.g., git.clone"
              aria-label={`Step ${index + 1} action`}
            />
            <label className={styles.stepMinCountLabel}>
              <span className={styles.stepMinCountText}>Min count</span>
              <input
                type="number"
                className={styles.stepMinCountInput}
                value={step.min_count}
                onChange={(e) => handleMinCountChange(index, e)}
                min={1}
                aria-label={`Step ${index + 1} minimum count`}
              />
            </label>
          </div>
          <div className={styles.stepControls}>
            <button
              type="button"
              className={styles.moveBtn}
              onClick={() => moveStep(index, -1)}
              disabled={index === 0}
              aria-label={`Move step ${index + 1} up`}
            >
              ↑
            </button>
            <button
              type="button"
              className={styles.moveBtn}
              onClick={() => moveStep(index, 1)}
              disabled={index === steps.length - 1}
              aria-label={`Move step ${index + 1} down`}
            >
              ↓
            </button>
            <button
              type="button"
              className={styles.removeBtn}
              onClick={() => removeStep(index)}
              aria-label={`Remove step ${index + 1}`}
            >
              ×
            </button>
          </div>
        </div>
      ))}
      <button type="button" className={styles.addBtn} onClick={addStep}>
        + Add step
      </button>
    </div>
  );
}
