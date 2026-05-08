import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '../../components/primitives/Button';
import { getNotificationPreferences, updateNotificationPreferences } from '../../api/notifications';
import type { NotificationPreferencesUpdate, NotificationSeverity } from '../../types/notifications';
import styles from './NotificationPreferences.module.css';

export function NotificationPreferences() {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);
  const [localOverrides, setLocalOverrides] = useState<NotificationPreferencesUpdate | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['notification-preferences'],
    queryFn: getNotificationPreferences,
  });

  const mutation = useMutation({
    mutationFn: updateNotificationPreferences,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['notification-preferences'] });
      setLocalOverrides(null);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    },
  });

  // Derive form state from server data + local overrides
  const form: NotificationPreferencesUpdate = {
    in_app_enabled: localOverrides?.in_app_enabled ?? data?.in_app_enabled ?? true,
    email_enabled: localOverrides?.email_enabled ?? data?.email_enabled ?? false,
    slack_enabled: localOverrides?.slack_enabled ?? data?.slack_enabled ?? false,
    severity_filter: localOverrides?.severity_filter ?? data?.severity_filter ?? 'info',
    detection_alerts: localOverrides?.detection_alerts ?? data?.detection_alerts ?? true,
    sync_alerts: localOverrides?.sync_alerts ?? data?.sync_alerts ?? true,
    system_alerts: localOverrides?.system_alerts ?? data?.system_alerts ?? true,
  };

  function handleToggle(field: keyof NotificationPreferencesUpdate) {
    setLocalOverrides((prev) => ({
      ...prev,
      [field]: !(form[field] as boolean),
    }));
  }

  function handleSeverityChange(value: NotificationSeverity) {
    setLocalOverrides((prev) => ({
      ...prev,
      severity_filter: value,
    }));
  }

  function handleSave() {
    mutation.mutate(form);
  }

  if (isLoading) return <div className={styles.loading}>Loading preferences…</div>;
  if (isError) return <div className={styles.error}>Failed to load preferences</div>;

  const hasChanges = localOverrides !== null;

  return (
    <div className={styles.prefsContainer}>
      <div className={styles.section}>
        <div className={styles.sectionTitle}>Delivery Channels</div>
        <div className={styles.sectionDesc}>Choose how you receive notifications</div>
        <div className={styles.fieldGroup}>
          <div className={styles.field}>
            <div>
              <div className={styles.fieldLabel}>In-app notifications</div>
              <div className={styles.fieldDesc}>Show notifications in the app</div>
            </div>
            <button
              className={`${styles.toggle}${form.in_app_enabled ? ` ${styles.toggleOn}` : ''}`}
              onClick={() => handleToggle('in_app_enabled')}
              role="switch"
              aria-checked={form.in_app_enabled ?? false}
              aria-label="In-app notifications"
            />
          </div>
          <div className={styles.field}>
            <div>
              <div className={styles.fieldLabel}>Email notifications</div>
              <div className={styles.fieldDesc}>Receive alerts via email</div>
            </div>
            <button
              className={`${styles.toggle}${form.email_enabled ? ` ${styles.toggleOn}` : ''}`}
              onClick={() => handleToggle('email_enabled')}
              role="switch"
              aria-checked={form.email_enabled ?? false}
              aria-label="Email notifications"
            />
          </div>
          <div className={styles.field}>
            <div>
              <div className={styles.fieldLabel}>Slack notifications</div>
              <div className={styles.fieldDesc}>Receive alerts in Slack</div>
            </div>
            <button
              className={`${styles.toggle}${form.slack_enabled ? ` ${styles.toggleOn}` : ''}`}
              onClick={() => handleToggle('slack_enabled')}
              role="switch"
              aria-checked={form.slack_enabled ?? false}
              aria-label="Slack notifications"
            />
          </div>
        </div>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>Minimum Severity</div>
        <div className={styles.sectionDesc}>
          Only receive notifications at or above this severity level
        </div>
        <select
          className={styles.selectField}
          value={form.severity_filter ?? 'info'}
          onChange={(e) => handleSeverityChange(e.target.value as NotificationSeverity)}
          aria-label="Minimum severity level"
        >
          <option value="info">Info (all notifications)</option>
          <option value="warning">Warning and above</option>
          <option value="critical">Critical only</option>
        </select>
      </div>

      <div className={styles.section}>
        <div className={styles.sectionTitle}>Alert Sources</div>
        <div className={styles.sectionDesc}>Choose which types of alerts you want to receive</div>
        <div className={styles.fieldGroup}>
          <div className={styles.field}>
            <div>
              <div className={styles.fieldLabel}>Detection alerts</div>
              <div className={styles.fieldDesc}>Threat detections and security findings</div>
            </div>
            <button
              className={`${styles.toggle}${form.detection_alerts ? ` ${styles.toggleOn}` : ''}`}
              onClick={() => handleToggle('detection_alerts')}
              role="switch"
              aria-checked={form.detection_alerts ?? false}
              aria-label="Detection alerts"
            />
          </div>
          <div className={styles.field}>
            <div>
              <div className={styles.fieldLabel}>Sync alerts</div>
              <div className={styles.fieldDesc}>Data synchronization status updates</div>
            </div>
            <button
              className={`${styles.toggle}${form.sync_alerts ? ` ${styles.toggleOn}` : ''}`}
              onClick={() => handleToggle('sync_alerts')}
              role="switch"
              aria-checked={form.sync_alerts ?? false}
              aria-label="Sync alerts"
            />
          </div>
          <div className={styles.field}>
            <div>
              <div className={styles.fieldLabel}>System alerts</div>
              <div className={styles.fieldDesc}>System health and maintenance notifications</div>
            </div>
            <button
              className={`${styles.toggle}${form.system_alerts ? ` ${styles.toggleOn}` : ''}`}
              onClick={() => handleToggle('system_alerts')}
              role="switch"
              aria-checked={form.system_alerts ?? false}
              aria-label="System alerts"
            />
          </div>
        </div>
      </div>

      <div className={styles.actions}>
        <Button
          variant="primary"
          size="sm"
          onClick={handleSave}
          disabled={!hasChanges || mutation.isPending}
        >
          {mutation.isPending ? 'Saving…' : 'Save preferences'}
        </Button>
      </div>
      {saved && <div className={styles.successMsg}>Preferences saved successfully</div>}
    </div>
  );
}
