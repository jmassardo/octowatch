import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getMaintenanceStatus,
  toggleMaintenanceMode,
  updateMaintenanceStatus,
  type MaintenanceSeverity,
} from '../../api/maintenance';
import { MaintenanceBanner } from '../../components/layout/MaintenanceBanner';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import { useToast } from '../../hooks/useToast';
import { formatAbsolute } from '../../utils/dates';
import styles from './Settings.module.css';

interface MaintenanceFormState {
  enabled: boolean;
  message: string;
  severity: MaintenanceSeverity;
  block_writes: boolean;
  estimated_end: string;
}

function toDateTimeLocal(value: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const adjusted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return adjusted.toISOString().slice(0, 16);
}

function toIsoString(value: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function toFormState(data?: {
  enabled: boolean;
  message: string;
  severity: MaintenanceSeverity;
  block_writes: boolean;
  estimated_end: string | null;
}): MaintenanceFormState {
  return {
    enabled: data?.enabled ?? false,
    message: data?.message ?? 'OctoWatch is undergoing scheduled maintenance.',
    severity: data?.severity ?? 'warning',
    block_writes: data?.block_writes ?? false,
    estimated_end: toDateTimeLocal(data?.estimated_end ?? null),
  };
}

export function MaintenanceSettingsPanel() {
  const qc = useQueryClient();
  const { showToast } = useToast();
  const [showPreview, setShowPreview] = useState(false);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['maintenance-status'],
    queryFn: getMaintenanceStatus,
  });
  const [draft, setDraft] = useState<MaintenanceFormState | null>(null);
  const baseForm = useMemo(() => toFormState(data), [data]);
  const form = draft ?? baseForm;
  const hasChanges = useMemo(() => {
    if (!data) return false;
    return JSON.stringify(form) !== JSON.stringify(baseForm);
  }, [baseForm, data, form]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateMaintenanceStatus({
        enabled: form.enabled,
        message: form.message.trim() || 'OctoWatch is undergoing scheduled maintenance.',
        severity: form.severity,
        block_writes: form.block_writes,
        estimated_end: toIsoString(form.estimated_end),
      }),
    onSuccess: (next) => {
      qc.setQueryData(['maintenance-status'], next);
      setDraft(null);
      showToast('Maintenance settings saved', 'success');
    },
    onError: () => {
      showToast('Failed to save maintenance settings', 'error');
    },
  });

  const toggleMutation = useMutation({
    mutationFn: () => toggleMaintenanceMode({ enabled: !data?.enabled }),
    onSuccess: (next) => {
      qc.setQueryData(['maintenance-status'], next);
      setDraft(null);
      showToast(next.enabled ? 'Maintenance mode enabled' : 'Maintenance mode disabled', 'success');
    },
    onError: () => {
      showToast('Failed to toggle maintenance mode', 'error');
    },
  });

  if (isLoading) return <Spinner />;
  if (isError || !data) {
    return (
      <div className={styles.configForm}>
        <div className={styles.configError}>Failed to load maintenance settings.</div>
        <div className={styles.categoryFormActions}>
          <Button size="sm" onClick={() => void refetch()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  const previewStatus = {
    enabled: true,
    message: form.message.trim() || 'OctoWatch is undergoing scheduled maintenance.',
    severity: form.severity,
    block_writes: form.block_writes,
    started_at: data.started_at,
    estimated_end: toIsoString(form.estimated_end),
  } as const;

  return (
    <section className={styles.featuresPane}>
      <p className={styles.featuresDescription}>
        Configure the global maintenance banner and optionally block write operations for non-admin
        users while maintenance is active.
      </p>
      <div className={styles.configForm}>
        <div className={styles.categoryFormRow}>
          <div className={styles.categoryFormInfo}>
            <label className={styles.categoryFormLabel} htmlFor="maintenance-enabled">
              Maintenance mode
            </label>
            <span className={styles.categoryFormHint}>
              Toggle the global maintenance banner for all authenticated users.
            </span>
          </div>
          <div className={styles.categoryFormControl}>
            <label className={styles.toggleSwitch}>
              <input
                id="maintenance-enabled"
                type="checkbox"
                checked={form.enabled}
                onChange={(event) =>
                  setDraft((current) => ({ ...(current ?? baseForm), enabled: event.target.checked }))
                }
              />
              <span className={styles.toggleSlider} />
            </label>
          </div>
        </div>

        <div className={styles.categoryFormRow}>
          <div className={styles.categoryFormInfo}>
            <label className={styles.categoryFormLabel} htmlFor="maintenance-message">
              Banner message
            </label>
            <span className={styles.categoryFormHint}>
              The user-facing message shown at the top of the application.
            </span>
          </div>
          <div className={styles.categoryFormControl}>
            <textarea
              id="maintenance-message"
              className={styles.categoryFormTextarea}
              value={form.message}
              onChange={(event) =>
                setDraft((current) => ({ ...(current ?? baseForm), message: event.target.value }))
              }
              rows={3}
            />
          </div>
        </div>

        <div className={styles.categoryFormRow}>
          <div className={styles.categoryFormInfo}>
            <label className={styles.categoryFormLabel} htmlFor="maintenance-severity">
              Severity level
            </label>
            <span className={styles.categoryFormHint}>
              Choose how prominently the banner should appear.
            </span>
          </div>
          <div className={styles.categoryFormControl}>
            <select
              id="maintenance-severity"
              className={styles.categoryFormSelect}
              value={form.severity}
              onChange={(event) =>
                setDraft((current) => ({
                  ...(current ?? baseForm),
                  severity: event.target.value as MaintenanceSeverity,
                }))
              }
            >
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
            </select>
          </div>
        </div>

        <div className={styles.categoryFormRow}>
          <div className={styles.categoryFormInfo}>
            <label className={styles.categoryFormLabel} htmlFor="maintenance-block-writes">
              Block write operations
            </label>
            <span className={styles.categoryFormHint}>
              When enabled, POST/PUT/DELETE requests from non-admin users return 503.
            </span>
          </div>
          <div className={styles.categoryFormControl}>
            <label className={styles.toggleSwitch}>
              <input
                id="maintenance-block-writes"
                type="checkbox"
                checked={form.block_writes}
                onChange={(event) =>
                  setDraft((current) => ({ ...(current ?? baseForm), block_writes: event.target.checked }))
                }
              />
              <span className={styles.toggleSlider} />
            </label>
          </div>
        </div>

        <div className={styles.categoryFormRow}>
          <div className={styles.categoryFormInfo}>
            <label className={styles.categoryFormLabel} htmlFor="maintenance-estimated-end">
              Estimated end time
            </label>
            <span className={styles.categoryFormHint}>
              Optional ETA shown to users in the maintenance banner.
            </span>
          </div>
          <div className={styles.categoryFormControl}>
            <input
              id="maintenance-estimated-end"
              className={styles.categoryFormInput}
              type="datetime-local"
              value={form.estimated_end}
              onChange={(event) =>
                setDraft((current) => ({ ...(current ?? baseForm), estimated_end: event.target.value }))
              }
            />
          </div>
        </div>

        <div className={styles.maintenanceMeta}>
          <span>Status: {data.enabled ? 'Active' : 'Inactive'}</span>
          <span>Started: {formatAbsolute(data.started_at)}</span>
          <span>ETA: {formatAbsolute(data.estimated_end)}</span>
        </div>

        <div className={styles.categoryFormActions}>
          <Button size="sm" onClick={() => setShowPreview((current) => !current)}>
            {showPreview ? 'Hide preview' : 'Preview banner'}
          </Button>
          <Button
            size="sm"
            onClick={() => toggleMutation.mutate()}
            disabled={toggleMutation.isPending}
          >
            {toggleMutation.isPending
              ? 'Updating…'
              : data.enabled
                ? 'Disable maintenance mode'
                : 'Enable maintenance mode'}
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || !hasChanges}
          >
            {saveMutation.isPending ? 'Saving…' : 'Save changes'}
          </Button>
        </div>
      </div>

      {showPreview && (
        <div className={styles.maintenancePreview}>
          <MaintenanceBanner status={previewStatus} polling={false} dismissible={false} />
        </div>
      )}
    </section>
  );
}
