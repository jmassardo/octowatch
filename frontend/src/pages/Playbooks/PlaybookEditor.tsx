import { useState } from 'react';
import type {
  CreateTemplatePayload,
  UpdateTemplatePayload,
  PlaybookStep,
  PlaybookTemplate,
} from '../../api/playbooks';
import { Button } from '../../components/primitives/Button';
import styles from './Playbooks.module.css';

const ACTION_TYPES = ['manual', 'link', 'manual_check', 'approval', 'automated', 'evidence'];

interface StepFormData {
  title: string;
  description: string;
  action_type: string;
  required: boolean;
}

function emptyStep(): StepFormData {
  return { title: '', description: '', action_type: 'manual', required: true };
}

interface PlaybookEditorProps {
  /** Existing template to edit, or undefined for create mode. */
  template?: PlaybookTemplate;
  /** Called when saving succeeds. */
  onSave: (data: CreateTemplatePayload | UpdateTemplatePayload) => void;
  /** Called when the user cancels. */
  onCancel: () => void;
  /** Whether a save request is in progress. */
  saving?: boolean;
}

/**
 * PlaybookEditor — Create or edit playbook templates.
 *
 * Supports adding, removing, and reordering steps. Each step has a
 * name, description, type, and required flag.
 */
export function PlaybookEditor({ template, onSave, onCancel, saving }: PlaybookEditorProps) {
  const [name, setName] = useState(template?.name ?? '');
  const [description, setDescription] = useState(template?.description ?? '');
  const [categories, setCategories] = useState(template?.detection_categories.join(', ') ?? '');
  const [steps, setSteps] = useState<StepFormData[]>(() => {
    if (template?.steps && template.steps.length > 0) {
      return template.steps.map((s: PlaybookStep) => ({
        title: s.title,
        description: s.description,
        action_type: s.action_type,
        required: s.required !== false,
      }));
    }
    return [emptyStep()];
  });
  const [previewMode, setPreviewMode] = useState(false);

  function updateStep(idx: number, field: keyof StepFormData, value: string | boolean) {
    setSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, [field]: value } : s)));
  }

  function addStep() {
    setSteps((prev) => [...prev, emptyStep()]);
  }

  function removeStep(idx: number) {
    if (steps.length <= 1) return;
    setSteps((prev) => prev.filter((_, i) => i !== idx));
  }

  function moveStep(idx: number, direction: 'up' | 'down') {
    const newIdx = direction === 'up' ? idx - 1 : idx + 1;
    if (newIdx < 0 || newIdx >= steps.length) return;
    const next = [...steps];
    const temp = next[idx]!;
    next[idx] = next[newIdx]!;
    next[newIdx] = temp;
    setSteps(next);
  }

  function handleSubmit() {
    const parsedCategories = categories
      .split(',')
      .map((c) => c.trim())
      .filter(Boolean);

    const payload: CreateTemplatePayload = {
      name,
      description: description || undefined,
      detection_categories: parsedCategories,
      steps: steps.map((s) => ({
        title: s.title,
        description: s.description,
        action_type: s.action_type,
        required: s.required,
      })),
    };

    onSave(payload);
  }

  const isValid = name.trim().length > 0 && steps.every((s) => s.title.trim().length > 0);

  if (previewMode) {
    return (
      <div className={styles.page}>
        <Button size="sm" onClick={() => setPreviewMode(false)}>
          ← Back to Editor
        </Button>
        <h2>{name || 'Untitled Playbook'}</h2>
        <p className={styles.stepDesc}>{description || 'No description'}</p>
        {steps.map((step, idx) => (
          <div key={idx} className={styles.stepCard}>
            <h3 className={styles.stepTitle}>
              Step {idx + 1}: {step.title}
            </h3>
            <p className={styles.stepDesc}>{step.description || 'No description'}</p>
            <span className={styles.stepBadge}>{step.action_type}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <Button size="sm" onClick={onCancel}>
          ← Cancel
        </Button>
        <Button size="sm" onClick={() => setPreviewMode(true)}>
          Preview
        </Button>
      </div>

      <h2>{template ? 'Edit Playbook Template' : 'Create Playbook Template'}</h2>

      <div className={styles.editorForm}>
        <div className={styles.formGroup}>
          <label className={styles.formLabel} htmlFor="pb-name">
            Name
          </label>
          <input
            id="pb-name"
            className={styles.formInput}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Account Compromise Response"
          />
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel} htmlFor="pb-desc">
            Description
          </label>
          <textarea
            id="pb-desc"
            className={styles.formTextarea}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe the playbook purpose…"
            rows={3}
          />
        </div>

        <div className={styles.formGroup}>
          <label className={styles.formLabel} htmlFor="pb-categories">
            Detection Categories (comma-separated)
          </label>
          <input
            id="pb-categories"
            className={styles.formInput}
            value={categories}
            onChange={(e) => setCategories(e.target.value)}
            placeholder="account_compromise, privilege_escalation"
          />
        </div>

        <div className={styles.formGroup}>
          <span className={styles.formLabel}>Steps</span>
          <div className={styles.stepList}>
            {steps.map((step, idx) => (
              <div key={idx} className={styles.stepItem} data-testid={`editor-step-${idx}`}>
                <div className={styles.stepItemHeader}>
                  <span className={styles.stepNumber}>#{idx + 1}</span>
                  <div className={styles.stepItemActions}>
                    <button
                      type="button"
                      className={styles.moveBtn}
                      onClick={() => moveStep(idx, 'up')}
                      disabled={idx === 0}
                      aria-label={`Move step ${idx + 1} up`}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className={styles.moveBtn}
                      onClick={() => moveStep(idx, 'down')}
                      disabled={idx === steps.length - 1}
                      aria-label={`Move step ${idx + 1} down`}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className={styles.removeBtn}
                      onClick={() => removeStep(idx)}
                      disabled={steps.length <= 1}
                      aria-label={`Remove step ${idx + 1}`}
                    >
                      ✕
                    </button>
                  </div>
                </div>
                <input
                  className={styles.formInput}
                  value={step.title}
                  onChange={(e) => updateStep(idx, 'title', e.target.value)}
                  placeholder="Step title"
                  style={{ marginBottom: 8 }}
                />
                <textarea
                  className={styles.formTextarea}
                  value={step.description}
                  onChange={(e) => updateStep(idx, 'description', e.target.value)}
                  placeholder="Step instructions…"
                  rows={2}
                  style={{ marginBottom: 8 }}
                />
                <select
                  className={styles.formSelect}
                  value={step.action_type}
                  onChange={(e) => updateStep(idx, 'action_type', e.target.value)}
                >
                  {ACTION_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
          <Button size="sm" onClick={addStep} style={{ alignSelf: 'flex-start' }}>
            + Add Step
          </Button>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <Button variant="primary" onClick={handleSubmit} disabled={!isValid || saving}>
            {saving ? 'Saving…' : template ? 'Update Template' : 'Create Template'}
          </Button>
          <Button onClick={onCancel}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}
