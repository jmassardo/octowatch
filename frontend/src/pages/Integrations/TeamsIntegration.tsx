import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getTeamsConfig,
  testTeamsConnection,
  updateTeamsConfig,
  type TeamsChannelKey,
  type TeamsConfigResponse,
  type TeamsConfigUpdate,
  type TeamsNotificationSource,
} from '../../api/teams';
import { Button } from '../../components/primitives/Button';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { useToast } from '../../hooks/useToast';
import styles from './TeamsIntegration.module.css';

const CHANNEL_LABELS: Record<TeamsChannelKey, string> = {
  default: 'Default channel',
  detections: 'Detections channel',
  sync_errors: 'Sync errors channel',
  system_health: 'System health channel',
  threat_intel: 'Threat intel channel',
};

const SOURCE_LABELS: Record<TeamsNotificationSource, string> = {
  detections: 'Detections',
  sync_errors: 'Sync errors',
  system_health: 'System health',
  threat_intel: 'Threat intel',
};

const CHANNEL_KEYS = Object.keys(CHANNEL_LABELS) as TeamsChannelKey[];

function toFormState(): TeamsConfigUpdate {
  return {
    channel_webhooks: {
      default: '',
      detections: '',
      sync_errors: '',
      system_health: '',
      threat_intel: '',
    },
    source_mappings: {
      detections: 'detections',
      sync_errors: 'sync_errors',
      system_health: 'system_health',
      threat_intel: 'threat_intel',
    },
    notification_settings: {
      detections: true,
      sync_errors: true,
      system_health: true,
      threat_intel: false,
    },
    clear_channels: [],
  };
}

function mergeConfig(config: TeamsConfigResponse): TeamsConfigUpdate {
  return {
    channel_webhooks: toFormState().channel_webhooks,
    source_mappings: config.source_mappings,
    notification_settings: config.notification_settings,
    clear_channels: [],
  };
}

export function TeamsIntegration() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [draft, setDraft] = useState<TeamsConfigUpdate | null>(null);
  const [testStatus, setTestStatus] = useState<{ state: 'success' | 'error'; message: string } | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['teams-config'],
    queryFn: getTeamsConfig,
  });

  const form = draft ?? (data ? mergeConfig(data) : null);

  const saveMutation = useMutation({
    mutationFn: () => updateTeamsConfig(form as TeamsConfigUpdate),
    onSuccess: (response) => {
      queryClient.setQueryData(['teams-config'], response);
      setDraft(null);
      setTestStatus(null);
      showToast('Teams configuration saved', 'success');
    },
    onError: () => {
      showToast('Failed to save Teams configuration', 'error');
    },
  });

  const testMutation = useMutation({
    mutationFn: () => testTeamsConnection(form?.source_mappings.detections ?? 'default'),
    onSuccess: (response) => {
      setTestStatus({ state: 'success', message: response.message });
      showToast('Teams test sent', 'success');
    },
    onError: () => {
      setTestStatus({ state: 'error', message: 'Teams test failed. Check the configured webhook URLs.' });
      showToast('Teams test failed', 'error');
    },
  });

  if (isLoading) {
    return (
      <Card>
        <div className={styles.panel}>
          <Spinner />
          <span>Loading Teams integration…</span>
        </div>
      </Card>
    );
  }

  if (isError) {
    return <ErrorBanner message={error instanceof Error ? error.message : 'Failed to load Teams integration'} />;
  }

  if (!data || !form) {
    return null;
  }

  const configuredCount = Object.values(data.channel_webhook_configured).filter(Boolean).length;

  return (
    <Card>
      <div className={styles.panel}>
        <div className={styles.header}>
          <div className={styles.titleGroup}>
            <h2 className={styles.title}>Microsoft Teams integration</h2>
            <p className={styles.description}>
              Deliver OctoWatch alerts to Teams channels with Adaptive Cards and source-specific routing.
            </p>
          </div>
          <div className={styles.statusRow}>
            <span className={styles.badge} data-state={configuredCount > 0 ? 'ready' : 'missing'}>
              {configuredCount} webhook{configuredCount === 1 ? '' : 's'} configured
            </span>
          </div>
        </div>

        <div className={styles.mappingSection}>
          <CardHeader>Channel webhooks</CardHeader>
          {CHANNEL_KEYS.map((channel) => (
            <div key={channel} className={styles.mappingRow}>
              <label className={styles.label} htmlFor={`teams-webhook-${channel}`}>
                {CHANNEL_LABELS[channel]}
              </label>
              <div className={styles.inputGroup}>
                <input
                  id={`teams-webhook-${channel}`}
                  className={styles.input}
                  type="password"
                  aria-label={`${CHANNEL_LABELS[channel]} webhook`}
                  value={form.channel_webhooks[channel]}
                  placeholder={data.channel_webhooks_masked[channel] ?? 'https://outlook.office.com/webhook/...'}
                  onChange={(event) =>
                    setDraft({
                      ...form,
                      channel_webhooks: {
                        ...form.channel_webhooks,
                        [channel]: event.target.value,
                      },
                      clear_channels: form.clear_channels.filter((value) => value !== channel),
                    })
                  }
                />
                {data.channel_webhook_configured[channel] && (
                  <Button
                    type="button"
                    size="sm"
                    onClick={() =>
                      setDraft({
                        ...form,
                        channel_webhooks: {
                          ...form.channel_webhooks,
                          [channel]: '',
                        },
                        clear_channels: Array.from(new Set([...form.clear_channels, channel])),
                      })
                    }
                  >
                    Clear
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className={styles.mappingSection}>
          <CardHeader>Source routing</CardHeader>
          {Object.entries(SOURCE_LABELS).map(([source, label]) => (
            <div key={source} className={styles.mappingRow}>
              <label className={styles.toggle}>
                <input
                  type="checkbox"
                  checked={form.notification_settings[source as TeamsNotificationSource]}
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
              <select
                className={styles.input}
                aria-label={`${label} channel mapping`}
                value={form.source_mappings[source as TeamsNotificationSource]}
                onChange={(event) =>
                  setDraft({
                    ...form,
                    source_mappings: {
                      ...form.source_mappings,
                      [source]: event.target.value as TeamsChannelKey,
                    },
                  })
                }
              >
                {CHANNEL_KEYS.map((channel) => (
                  <option key={channel} value={channel}>
                    {CHANNEL_LABELS[channel]}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>

        <div className={styles.actions}>
          <Button variant="primary" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
            {saveMutation.isPending ? 'Saving…' : 'Save Teams settings'}
          </Button>
          <Button onClick={() => testMutation.mutate()} disabled={testMutation.isPending}>
            {testMutation.isPending ? 'Testing…' : 'Test message'}
          </Button>
          {testStatus && (
            <span className={styles.testStatus} data-state={testStatus.state}>
              {testStatus.message}
            </span>
          )}
          {saveMutation.isError && <span className={styles.error}>Unable to save Teams settings.</span>}
        </div>
      </div>
    </Card>
  );
}
