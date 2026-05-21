/**
 * CreateCustomWidgetDialog — modal dialog for creating a new custom query widget.
 *
 * Users can either select a saved query or write inline SQL, choose a
 * visualization type, set a title, and configure the auto-refresh interval.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Modal } from '../primitives/Modal';
import { Button } from '../primitives/Button';
import { listSavedQueries } from '../../api/query';
import { VISUALIZATION_TYPE_OPTIONS, type VisualizationType } from '../../types/customWidget';
import { createCustomWidgetConfig } from './customWidgetConfigStorage';
import styles from './Widgets.module.css';

interface CreateCustomWidgetDialogProps {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly onCreated: (widgetId: string) => void;
}

/** Inner form component that resets state cleanly via key-based remounting. */
function CreateCustomWidgetForm({
  onClose,
  onCreated,
}: {
  readonly onClose: () => void;
  readonly onCreated: (widgetId: string) => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [querySource, setQuerySource] = useState<'saved' | 'inline'>('saved');
  const [selectedQueryId, setSelectedQueryId] = useState<number | null>(null);
  const [inlineSql, setInlineSql] = useState('');
  const [visualizationType, setVisualizationType] = useState<VisualizationType>('bar');
  const [refreshInterval, setRefreshInterval] = useState(0);
  const [validationError, setValidationError] = useState('');

  const { data: savedQueries } = useQuery({
    queryKey: ['saved-queries-for-widget'],
    queryFn: listSavedQueries,
    staleTime: 30_000,
  });

  function handleQuerySelect(queryId: number | null) {
    setSelectedQueryId(queryId);
    // Auto-fill title from selected saved query
    if (queryId && savedQueries && !title) {
      const query = savedQueries.find((q) => q.id === queryId);
      if (query) {
        setTitle(query.name);
      }
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setValidationError('');

    if (!title.trim()) {
      setValidationError('Title is required');
      return;
    }

    if (querySource === 'saved' && !selectedQueryId) {
      setValidationError('Please select a saved query');
      return;
    }

    if (querySource === 'inline' && !inlineSql.trim()) {
      setValidationError('Please enter a SQL query');
      return;
    }

    // Resolve SQL text
    let sqlText = inlineSql;
    if (querySource === 'saved' && selectedQueryId && savedQueries) {
      const query = savedQueries.find((q) => q.id === selectedQueryId);
      sqlText = query?.sql_text ?? '';
    }

    const config = createCustomWidgetConfig({
      title: title.trim(),
      description: description.trim() || undefined,
      savedQueryId: querySource === 'saved' ? selectedQueryId : null,
      inlineSql: sqlText,
      visualizationType,
      refreshIntervalSeconds: refreshInterval,
    });

    onCreated(config.id);
    onClose();
  }

  return (
    <form onSubmit={handleSubmit} className={styles.customWidgetForm}>
      {validationError && (
        <div className={styles.formError} role="alert">
          {validationError}
        </div>
      )}

      <div className={styles.formField}>
        <label htmlFor="widget-title" className={styles.formLabel}>
          Widget title
        </label>
        <input
          id="widget-title"
          type="text"
          className={styles.formInput}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g., Weekly Event Counts"
          maxLength={100}
        />
      </div>

      <div className={styles.formField}>
        <label htmlFor="widget-description" className={styles.formLabel}>
          Description (optional)
        </label>
        <input
          id="widget-description"
          type="text"
          className={styles.formInput}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Brief description of what this widget shows"
          maxLength={200}
        />
      </div>

      <fieldset className={styles.formFieldset}>
        <legend className={styles.formLabel}>Query source</legend>
        <div className={styles.radioGroup}>
          <label className={styles.radioLabel}>
            <input
              type="radio"
              name="querySource"
              value="saved"
              checked={querySource === 'saved'}
              onChange={() => setQuerySource('saved')}
            />
            Saved query
          </label>
          <label className={styles.radioLabel}>
            <input
              type="radio"
              name="querySource"
              value="inline"
              checked={querySource === 'inline'}
              onChange={() => setQuerySource('inline')}
            />
            Write SQL inline
          </label>
        </div>
      </fieldset>

      {querySource === 'saved' && (
        <div className={styles.formField}>
          <label htmlFor="saved-query-select" className={styles.formLabel}>
            Select a saved query
          </label>
          <select
            id="saved-query-select"
            className={styles.formSelect}
            value={selectedQueryId ?? ''}
            onChange={(e) => handleQuerySelect(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">— Choose a query —</option>
            {savedQueries?.map((q) => (
              <option key={q.id} value={q.id}>
                {q.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {querySource === 'inline' && (
        <div className={styles.formField}>
          <label htmlFor="inline-sql" className={styles.formLabel}>
            SQL query
          </label>
          <textarea
            id="inline-sql"
            className={styles.formTextarea}
            value={inlineSql}
            onChange={(e) => setInlineSql(e.target.value)}
            placeholder="SELECT action, COUNT(*) as count FROM audit_events GROUP BY action LIMIT 10"
            rows={4}
          />
        </div>
      )}

      <div className={styles.formField}>
        <label htmlFor="viz-type" className={styles.formLabel}>
          Visualization type
        </label>
        <select
          id="viz-type"
          className={styles.formSelect}
          value={visualizationType}
          onChange={(e) => setVisualizationType(e.target.value as VisualizationType)}
        >
          {VISUALIZATION_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label} — {opt.description}
            </option>
          ))}
        </select>
      </div>

      <div className={styles.formField}>
        <label htmlFor="refresh-interval" className={styles.formLabel}>
          Auto-refresh interval (seconds)
        </label>
        <input
          id="refresh-interval"
          type="number"
          className={styles.formInput}
          value={refreshInterval}
          onChange={(e) => setRefreshInterval(Math.max(0, Number(e.target.value) || 0))}
          min={0}
          max={3600}
          step={10}
        />
        <span className={styles.formHint}>
          {refreshInterval === 0
            ? 'Widget refreshes on page load only'
            : `Widget refreshes every ${refreshInterval}s`}
        </span>
      </div>

      <div className={styles.formActions}>
        <Button type="button" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" variant="primary">
          Create widget
        </Button>
      </div>
    </form>
  );
}

export function CreateCustomWidgetDialog({
  open,
  onClose,
  onCreated,
}: CreateCustomWidgetDialogProps) {
  // Use a key to force remount (and full state reset) each time dialog opens
  const [formKey, setFormKey] = useState(0);

  function handleClose() {
    onClose();
    setFormKey((k) => k + 1);
  }

  function handleCreated(widgetId: string) {
    onCreated(widgetId);
    setFormKey((k) => k + 1);
  }

  return (
    <Modal open={open} onClose={handleClose} title="Create custom widget" width={640}>
      <CreateCustomWidgetForm key={formKey} onClose={handleClose} onCreated={handleCreated} />
    </Modal>
  );
}
