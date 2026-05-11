import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getSlackConfig,
  testSlackConnection,
  updateSlackConfig,
  type SlackConfigResponse,
  type SlackConfigUpdate,
  type SlackNotificationSource,
} from '../../api/slack';
import { Button } from '../../components/primitives/Button';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import { useToast } from '../../hooks/useToast';
import styles from './SlackIntegration.module.css';

const SOURCE_LABELS: Record<SlackNotificationSource, string> = {
  detections: 'Detections',
  sync_errors: 'Sync errors',
  system_health: 'System health',
  threat_intel: 'Threat intel',
};

function toFormState(config: SlackConfigResponse): SlackConfigUpdate {
  return {
    default_channel: config.default_channel,
    channel_mappings: config.channel_mappings,
    notification_settings: config.notification_settings,
  };
}

export function SlackIntegration() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [botToken, setBotToken] = useState('');
  const [signingSecret, setSigningSecret] = useState('');
  const [draft, setDraft] = useState<SlackConfigUpdate | null>(null);
  const [testStatus, setTestStatus] = useState<{
    state: 'success' | 'error';
    message: string;
  } | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['slack-config'],
    queryFn: getSlackConfig,
  });

  const saveMutation = useMutation({
    mutationFn: () =>
      updateSlackConfig({
        ...form,
        bot_token: botToken.trim() || undefined,
        signing_secret: signingSecret.trim() || undefined,
      }),
    onSuccess: (response) => {
      queryClient.setQueryData(['slack-config'], response);
      setDraft(null);
      setBotToken('');
      setSigningSecret('');
      setTestStatus(null);
      showToast('Slack configuration saved', 'success');
    },
    onError: () => {
      showToast('Failed to save Slack configuration', 'error');
    },
  });

  const testMutation = useMutation({
    mutationFn: testSlackConnection,
    onSuccess: (response) => {
      setTestStatus({ state: 'success', message: response.message });
      showToast('Slack test sent', 'success');
    },
    onError: () => {
      setTestStatus({
        state: 'error',
        message: 'Slack test failed. Check the token and default channel.',
      });
      showToast('Slack test failed', 'error');
    },
  });

  if (isLoading) {
    return (
      <Card>
        <div className={styles.panel}>
          <Spinner />
          <span>Loading Slack integration…</span>
        </div>
      </Card>
    );
  }

  if (isError) {
    return (
      <ErrorBanner
        message={error instanceof Error ? error.message : 'Failed to load Slack integration'}
      />
    );
  }

  if (!data) {
    return null;
  }

  const form = draft ?? toFormState(data);

  return (
    <Card>
      <div className={styles.panel}>
        <div className={styles.header}>
          <div className={styles.titleGroup}>
            <h2 className={styles.title}>Slack integration</h2>
            <p className={styles.description}>
              Deliver OctoWatch alerts to Slack and enable the /octowatch slash command for quick
              lookups.
            </p>
          </div>
          <div className={styles.statusRow}>
            <span
              className={styles.badge}
              data-state={data.bot_token_configured ? 'ready' : 'missing'}
            >
              Bot token {data.bot_token_configured ? 'configured' : 'missing'}
            </span>
            <span
              className={styles.badge}
              data-state={data.signing_secret_configured ? 'ready' : 'missing'}
            >
              Signing secret {data.signing_secret_configured ? 'configured' : 'missing'}
            </span>
          </div>
        </div>

        <div className={styles.grid}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="slack-bot-token">
              Bot token
            </label>
            <input
              id="slack-bot-token"
              className={styles.input}
              type="password"
              value={botToken}
              onChange={(event) => setBotToken(event.target.value)}
              placeholder={data.bot_token_masked ?? 'xoxb-…'}
            />
            <span className={styles.help}>Leave blank to keep the existing token.</span>
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="slack-signing-secret">
              Signing secret
            </label>
            <input
              id="slack-signing-secret"
              className={styles.input}
              type="password"
              value={signingSecret}
              onChange={(event) => setSigningSecret(event.target.value)}
              placeholder={data.signing_secret_masked ?? '••••••••'}
            />
            <span className={styles.help}>
              Used to verify Slack Events, slash commands, and interactions.
            </span>
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="slack-default-channel">
              Default channel
            </label>
            <input
              id="slack-default-channel"
              className={styles.input}
              value={form.default_channel}
              onChange={(event) => setDraft({ ...form, default_channel: event.target.value })}
              placeholder="#security-alerts"
            />
            <span className={styles.help}>
              Fallback channel when a source-specific mapping is not set.
            </span>
          </div>
        </div>

        <div className={styles.mappingSection}>
          <CardHeader>Channel mapping</CardHeader>
          {Object.entries(SOURCE_LABELS).map(([source, label]) => (
            <div key={source} className={styles.mappingRow}>
              <label className={styles.toggle}>
                <input
                  type="checkbox"
                  checked={form.notification_settings[source as SlackNotificationSource]}
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
              <input
                className={styles.input}
                aria-label={`${label} channel`}
                value={form.channel_mappings[source as SlackNotificationSource]}
                onChange={(event) =>
                  setDraft({
                    ...form,
                    channel_mappings: {
                      ...form.channel_mappings,
                      [source]: event.target.value,
                    },
                  })
                }
                placeholder={form.default_channel || '#channel-name'}
              />
            </div>
          ))}
        </div>

        <div className={styles.actions}>
          <Button
            variant="primary"
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? 'Saving…' : 'Save Slack settings'}
          </Button>
          <Button onClick={() => testMutation.mutate()} disabled={testMutation.isPending}>
            {testMutation.isPending ? 'Testing…' : 'Test connection'}
          </Button>
          {testStatus && (
            <span className={styles.testStatus} data-state={testStatus.state}>
              {testStatus.message}
            </span>
          )}
          {saveMutation.isError && (
            <span className={styles.error}>Unable to save Slack settings.</span>
          )}
        </div>

        <div className={styles.mappingSection}>
          <CardHeader>
            <a href={data.installation_url} target="_blank" rel="noreferrer">
              Slack app installation guide
            </a>
          </CardHeader>
          <ol className={styles.instructions}>
            {data.installation_instructions.map((instruction) => (
              <li key={instruction}>{instruction}</li>
            ))}
          </ol>
          <div className={styles.commandList}>
            {data.commands.map((command) => (
              <span key={command} className={styles.command}>
                {command}
              </span>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}
