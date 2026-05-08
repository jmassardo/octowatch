import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getPagerDutyConfig,
  testPagerDutyConnection,
  updatePagerDutyConfig,
  type OctoWatchSeverity,
  type PagerDutyConfigResponse,
  type PagerDutyConfigUpdate,
  type PagerDutyNotificationSource,
  type PagerDutySeverity,
} from '../../api/pagerduty';
import { Button } from '../../components/primitives/Button';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { useToast } from '../../hooks/useToast';
import styles from './PagerDutyIntegration.module.css';

const SOURCE_LABELS: Record<PagerDutyNotificationSource, string> = {
  detections: 'Detections',
  sync_errors: 'Sync errors',
  system_health: 'System health',
  threat_intel: 'Threat intel',
};

const SEVERITY_OPTIONS: PagerDutySeverity[] = ['critical', 'error', 'warning', 'info'];
const OCTOWATCH_SEVERITIES: OctoWatchSeverity[] = ['critical', 'high', 'medium', 'low', 'info'];

function toFormState(config: PagerDutyConfigResponse): PagerDutyConfigUpdate {
  return {
    severity_mapping: config.severity_mapping,
    notification_settings: config.notification_settings,
    auto_resolve: config.auto_resolve,
  };
}

export function PagerDutyIntegration() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [routingKey, setRoutingKey] = useState('');
  const [draft, setDraft] = useState<PagerDutyConfigUpdate | null>(null);
  const [testStatus, setTestStatus] = useState<{ state: 'success' | 'error'; message: string } | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['pagerduty-config'],
    queryFn: getPagerDutyConfig,
  });

  const form = draft ?? (data ? toFormState(data) : null);

  const saveMutation = useMutation({
    mutationFn: () =>
      updatePagerDutyConfig({
        ...(form as PagerDutyConfigUpdate),
        routing_key: routingKey.trim() || undefined,
      }),
    onSuccess: (response) => {
      queryClient.setQueryData(['pagerduty-config'], response);
      setDraft(null);
      setRoutingKey('');
      setTestStatus(null);
      showToast('PagerDuty configuration saved', 'success');
    },
    onError: () => {
      showToast('Failed to save PagerDuty configuration', 'error');
    },
  });

  const testMutation = useMutation({
    mutationFn: testPagerDutyConnection,
    onSuccess: (response) => {
      setTestStatus({ state: 'success', message: response.message });
      showToast('PagerDuty test sent', 'success');
    },
    onError: () => {
      setTestStatus({ state: 'error', message: 'PagerDuty test failed. Check the routing key.' });
      showToast('PagerDuty test failed', 'error');
    },
  });

  if (isLoading) {
    return (
      <Card>
        <div className={styles.panel}>
          <Spinner />
          <span>Loading PagerDuty integration…</span>
        </div>
      </Card>
    );
  }

  if (isError) {
    return <ErrorBanner message={error instanceof Error ? error.message : 'Failed to load PagerDuty integration'} />;
  }

  if (!data || !form) {
    return null;
  }

  return (
    <Card>
      <div className={styles.panel}>
        <div className={styles.header}>
          <div className={styles.titleGroup}>
            <h2 className={styles.title}>PagerDuty integration</h2>
            <p className={styles.description}>
              Trigger PagerDuty incidents for OctoWatch alerts and optionally auto-resolve them when detections close.
            </p>
          </div>
          <div className={styles.statusRow}>
            <span className={styles.badge} data-state={data.routing_key_configured ? 'ready' : 'missing'}>
              Routing key {data.routing_key_configured ? 'configured' : 'missing'}
            </span>
            <span className={styles.badge} data-state={form.auto_resolve ? 'ready' : 'missing'}>
              Auto-resolve {form.auto_resolve ? 'enabled' : 'disabled'}
            </span>
          </div>
        </div>

        <div className={styles.grid}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="pagerduty-routing-key">
              Routing key
            </label>
            <input
              id="pagerduty-routing-key"
              className={styles.input}
              type="password"
              value={routingKey}
              onChange={(event) => setRoutingKey(event.target.value)}
              placeholder={data.routing_key_masked ?? '••••••••••••'}
            />
            <span className={styles.help}>Leave blank to keep the existing PagerDuty integration key.</span>
          </div>

          <label className={styles.toggle}>
            <input
              type="checkbox"
              checked={form.auto_resolve}
              onChange={(event) => setDraft({ ...form, auto_resolve: event.target.checked })}
            />
            Resolve incidents when a detection is marked resolved
          </label>
        </div>

        <div className={styles.mappingSection}>
          <CardHeader>Severity mapping</CardHeader>
          {OCTOWATCH_SEVERITIES.map((severity) => (
            <div key={severity} className={styles.mappingRow}>
              <label className={styles.label} htmlFor={`pagerduty-severity-${severity}`}>
                {severity.charAt(0).toUpperCase() + severity.slice(1)}
              </label>
              <select
                id={`pagerduty-severity-${severity}`}
                className={styles.input}
                aria-label={`${severity} severity mapping`}
                value={form.severity_mapping[severity]}
                onChange={(event) =>
                  setDraft({
                    ...form,
                    severity_mapping: {
                      ...form.severity_mapping,
                      [severity]: event.target.value as PagerDutySeverity,
                    },
                  })
                }
              >
                {SEVERITY_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>

        <div className={styles.mappingSection}>
          <CardHeader>Notification sources</CardHeader>
          {Object.entries(SOURCE_LABELS).map(([source, label]) => (
            <label key={source} className={styles.toggle}>
              <input
                type="checkbox"
                checked={form.notification_settings[source as PagerDutyNotificationSource]}
                onChange={(event) =>
                  setDraft({
                    ...form,
                    notification_settings: {
                      ...form.notification_settings,
                      [source]: event.target.checked,
                    },
                  })
                }
              />
              Enable {label}
            </label>
          ))}
        </div>

        <div className={styles.actions}>
          <Button variant="primary" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
            {saveMutation.isPending ? 'Saving…' : 'Save PagerDuty settings'}
          </Button>
          <Button onClick={() => testMutation.mutate()} disabled={testMutation.isPending}>
            {testMutation.isPending ? 'Testing…' : 'Test connection'}
          </Button>
          {testStatus && (
            <span className={styles.testStatus} data-state={testStatus.state}>
              {testStatus.message}
            </span>
          )}
          {saveMutation.isError && <span className={styles.error}>Unable to save PagerDuty settings.</span>}
        </div>
      </div>
    </Card>
  );
}
