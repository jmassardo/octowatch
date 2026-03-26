import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  listTicketingConfigs,
  createTicketingConfig,
  deleteTicketingConfig,
  listNotificationConfigs,
  createNotificationConfig,
  deleteNotificationConfig,
} from '../../api/integrations';
import type { TicketingConfigCreate, NotificationConfigCreate } from '../../types/integrations';
import { Button } from '../../components/primitives/Button';
import { Modal } from '../../components/primitives/Modal';
import { ConfirmDialog } from '../../components/primitives/ConfirmDialog';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Integrations.module.css';

function JiraForm({ onSave, onCancel }: { onSave: (v: TicketingConfigCreate) => void; onCancel: () => void }) {
  const [displayName, setDisplayName] = useState('Jira');
  const [target, setTarget] = useState('');
  const [projectKey, setProjectKey] = useState('');
  const [credVar, setCredVar] = useState('JIRA_API_TOKEN');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSave({ provider: 'jira', display_name: displayName, target, project_key: projectKey, credential_env_var: credVar });
  }

  return (
    <form onSubmit={handleSubmit} className={styles.intForm}>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Display name</label>
        <input className={styles.formInput} value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Jira base URL</label>
        <input className={styles.formInput} value={target} onChange={(e) => setTarget(e.target.value)} required placeholder="https://yourorg.atlassian.net" />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Project key</label>
        <input className={styles.formInput} value={projectKey} onChange={(e) => setProjectKey(e.target.value)} placeholder="SEC" />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Credential env var</label>
        <input className={styles.formInput} value={credVar} onChange={(e) => setCredVar(e.target.value)} required placeholder="JIRA_API_TOKEN" />
        <span className={styles.formHint}>Server-side env variable containing the API token</span>
      </div>
      <div className={styles.formActions}>
        <Button variant="default" onClick={onCancel} type="button">Cancel</Button>
        <Button variant="primary" type="submit">Connect</Button>
      </div>
    </form>
  );
}

function GhIssuesForm({ onSave, onCancel }: { onSave: (v: TicketingConfigCreate) => void; onCancel: () => void }) {
  const [displayName, setDisplayName] = useState('GitHub Issues');
  const [target, setTarget] = useState('');
  const [credVar, setCredVar] = useState('GH_ISSUES_TOKEN');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSave({ provider: 'github_issues', display_name: displayName, target, credential_env_var: credVar });
  }

  return (
    <form onSubmit={handleSubmit} className={styles.intForm}>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Display name</label>
        <input className={styles.formInput} value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Repo (owner/repo)</label>
        <input className={styles.formInput} value={target} onChange={(e) => setTarget(e.target.value)} required placeholder="your-org/security-issues" />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Credential env var</label>
        <input className={styles.formInput} value={credVar} onChange={(e) => setCredVar(e.target.value)} required placeholder="GH_ISSUES_TOKEN" />
      </div>
      <div className={styles.formActions}>
        <Button variant="default" onClick={onCancel} type="button">Cancel</Button>
        <Button variant="primary" type="submit">Connect</Button>
      </div>
    </form>
  );
}

function SlackForm({ onSave, onCancel }: { onSave: (v: NotificationConfigCreate) => void; onCancel: () => void }) {
  const [displayName, setDisplayName] = useState('Slack');
  const [target, setTarget] = useState('');
  const [credVar, setCredVar] = useState('SLACK_WEBHOOK_URL');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSave({ channel_type: 'slack', display_name: displayName, target, credential_env_var: credVar });
  }

  return (
    <form onSubmit={handleSubmit} className={styles.intForm}>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Display name</label>
        <input className={styles.formInput} value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Channel</label>
        <input className={styles.formInput} value={target} onChange={(e) => setTarget(e.target.value)} required placeholder="#security-alerts" />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Webhook URL env var</label>
        <input className={styles.formInput} value={credVar} onChange={(e) => setCredVar(e.target.value)} required placeholder="SLACK_WEBHOOK_URL" />
      </div>
      <div className={styles.formActions}>
        <Button variant="default" onClick={onCancel} type="button">Cancel</Button>
        <Button variant="primary" type="submit">Connect</Button>
      </div>
    </form>
  );
}

function EmailForm({ onSave, onCancel }: { onSave: (v: NotificationConfigCreate) => void; onCancel: () => void }) {
  const [displayName, setDisplayName] = useState('Email');
  const [target, setTarget] = useState('');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSave({ channel_type: 'email', display_name: displayName, target });
  }

  return (
    <form onSubmit={handleSubmit} className={styles.intForm}>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Display name</label>
        <input className={styles.formInput} value={displayName} onChange={(e) => setDisplayName(e.target.value)} required />
      </div>
      <div className={styles.formRow}>
        <label className={styles.formLabel}>Email address</label>
        <input className={styles.formInput} type="email" value={target} onChange={(e) => setTarget(e.target.value)} required placeholder="security@yourorg.com" />
      </div>
      <div className={styles.formActions}>
        <Button variant="default" onClick={onCancel} type="button">Cancel</Button>
        <Button variant="primary" type="submit">Connect</Button>
      </div>
    </form>
  );
}

function IntCard({
  name,
  description,
  icon,
  connected,
  connectedName,
  onConnect,
  onDisconnect,
}: {
  name: string;
  description: string;
  icon: React.ReactNode;
  connected: boolean;
  connectedName?: string;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  return (
    <div className={[styles.intCard, connected ? styles.intCardConnected : ''].join(' ')}>
      <div className={styles.intCardIcon}>{icon}</div>
      <div className={styles.intCardBody}>
        <div className={styles.intCardName}>{name}</div>
        <div className={styles.intCardDesc}>
          {connected ? (connectedName ?? name) : description}
        </div>
      </div>
      <div className={styles.intCardAction}>
        {connected ? (
          <Button variant="danger" size="sm" onClick={onDisconnect}>Disconnect</Button>
        ) : (
          <Button variant="primary" size="sm" onClick={onConnect}>Connect</Button>
        )}
      </div>
    </div>
  );
}

type ActiveModal = 'jira' | 'github_issues' | 'slack' | 'email' | null;

export function IntegrationsPage() {
  const qc = useQueryClient();
  const [activeModal, setActiveModal] = useState<ActiveModal>(null);
  const [deleteTicketing, setDeleteTicketing] = useState<number | null>(null);
  const [deleteNotif, setDeleteNotif] = useState<number | null>(null);

  const { data: ticketing, isLoading: tLoading, isError: tError } = useQuery({
    queryKey: ['ticketing-configs'],
    queryFn: listTicketingConfigs,
  });

  const { data: notifications, isLoading: nLoading, isError: nError } = useQuery({
    queryKey: ['notification-configs'],
    queryFn: listNotificationConfigs,
  });

  const createTicketMutation = useMutation({
    mutationFn: createTicketingConfig,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ticketing-configs'] }); setActiveModal(null); },
  });

  const deleteTicketMutation = useMutation({
    mutationFn: (id: number) => deleteTicketingConfig(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['ticketing-configs'] }); setDeleteTicketing(null); },
  });

  const createNotifMutation = useMutation({
    mutationFn: createNotificationConfig,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['notification-configs'] }); setActiveModal(null); },
  });

  const deleteNotifMutation = useMutation({
    mutationFn: (id: number) => deleteNotificationConfig(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['notification-configs'] }); setDeleteNotif(null); },
  });

  const jiraConfig = ticketing?.find((t) => t.provider === 'jira');
  const ghIssuesConfig = ticketing?.find((t) => t.provider === 'github_issues');
  const slackConfig = notifications?.find((n) => n.channel_type === 'slack');
  const emailConfig = notifications?.find((n) => n.channel_type === 'email');

  const isLoading = tLoading || nLoading;
  const isError = tError || nError;

  return (
    <div className={styles.page}>
      <div>
        <h1 className={styles.pageTitle}>Integrations</h1>
        <p className={styles.pageSub}>Connect external services for ticketing and notifications</p>
      </div>

      {isError && <ErrorBanner message="Failed to load integrations" onRetry={() => {}} />}

      {isLoading ? (
        <Spinner />
      ) : (
        <>
          <section>
            <h2 className={styles.sectionTitle}>Ticketing</h2>
            <div className={styles.mktGrid}>
              <IntCard
                name="Jira"
                description="Automatically create Jira issues for security detections"
                icon={<JiraIcon />}
                connected={!!jiraConfig}
                connectedName={jiraConfig?.display_name}
                onConnect={() => setActiveModal('jira')}
                onDisconnect={() => jiraConfig && setDeleteTicketing(jiraConfig.id)}
              />
              <IntCard
                name="GitHub Issues"
                description="File GitHub Issues for detections in a security repository"
                icon={<GhIcon />}
                connected={!!ghIssuesConfig}
                connectedName={ghIssuesConfig?.display_name}
                onConnect={() => setActiveModal('github_issues')}
                onDisconnect={() => ghIssuesConfig && setDeleteTicketing(ghIssuesConfig.id)}
              />
            </div>
          </section>

          <section>
            <h2 className={styles.sectionTitle}>Notifications</h2>
            <div className={styles.mktGrid}>
              <IntCard
                name="Slack"
                description="Send alert notifications to a Slack channel"
                icon={<SlackIcon />}
                connected={!!slackConfig}
                connectedName={slackConfig?.display_name}
                onConnect={() => setActiveModal('slack')}
                onDisconnect={() => slackConfig && setDeleteNotif(slackConfig.id)}
              />
              <IntCard
                name="Email"
                description="Send alert emails to a security distribution list"
                icon={<EmailIcon />}
                connected={!!emailConfig}
                connectedName={emailConfig?.display_name}
                onConnect={() => setActiveModal('email')}
                onDisconnect={() => emailConfig && setDeleteNotif(emailConfig.id)}
              />
            </div>
          </section>
        </>
      )}

      <Modal open={activeModal === 'jira'} onClose={() => setActiveModal(null)} title="Connect Jira">
        <JiraForm onSave={(v) => createTicketMutation.mutate(v)} onCancel={() => setActiveModal(null)} />
      </Modal>

      <Modal open={activeModal === 'github_issues'} onClose={() => setActiveModal(null)} title="Connect GitHub Issues">
        <GhIssuesForm onSave={(v) => createTicketMutation.mutate(v)} onCancel={() => setActiveModal(null)} />
      </Modal>

      <Modal open={activeModal === 'slack'} onClose={() => setActiveModal(null)} title="Connect Slack">
        <SlackForm onSave={(v) => createNotifMutation.mutate(v)} onCancel={() => setActiveModal(null)} />
      </Modal>

      <Modal open={activeModal === 'email'} onClose={() => setActiveModal(null)} title="Connect Email">
        <EmailForm onSave={(v) => createNotifMutation.mutate(v)} onCancel={() => setActiveModal(null)} />
      </Modal>

      <ConfirmDialog
        open={deleteTicketing !== null}
        onClose={() => setDeleteTicketing(null)}
        title="Disconnect integration"
        message="Disconnect this integration? Active workflows using it may stop working."
        confirmLabel="Disconnect"
        confirmVariant="danger"
        onConfirm={() => deleteTicketing !== null && deleteTicketMutation.mutate(deleteTicketing)}
      />

      <ConfirmDialog
        open={deleteNotif !== null}
        onClose={() => setDeleteNotif(null)}
        title="Disconnect integration"
        message="Disconnect this notification channel?"
        confirmLabel="Disconnect"
        confirmVariant="danger"
        onConfirm={() => deleteNotif !== null && deleteNotifMutation.mutate(deleteNotif)}
      />
    </div>
  );
}

function JiraIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
      <rect width="28" height="28" rx="6" fill="#0052CC" />
      <path d="M14 5L7 14l7 3 7-3L14 5z" fill="white" fillOpacity=".8" />
      <path d="M14 14l-7 3 7 6 7-6-7-3z" fill="white" />
    </svg>
  );
}

function GhIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
      <rect width="28" height="28" rx="6" fill="#24292e" />
      <path d="M14 4a10 10 0 00-3.16 19.49c.5.09.68-.22.68-.48v-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.89 1.52 2.34 1.08 2.91.83.09-.65.35-1.08.63-1.33-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02A9.56 9.56 0 0114 8.84c.85 0 1.71.12 2.51.34 1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.69-4.57 4.93.36.31.68.92.68 1.85v2.74c0 .27.18.58.69.48A10 10 0 0014 4z" fill="white" />
    </svg>
  );
}

function SlackIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
      <rect width="28" height="28" rx="6" fill="#4A154B" />
      <circle cx="10" cy="14" r="2" fill="#E01E5A" />
      <circle cx="14" cy="10" r="2" fill="#36C5F0" />
      <circle cx="18" cy="14" r="2" fill="#2EB67D" />
      <circle cx="14" cy="18" r="2" fill="#ECB22E" />
    </svg>
  );
}

function EmailIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
      <rect width="28" height="28" rx="6" fill="#30363d" />
      <rect x="5" y="8" width="18" height="12" rx="2" stroke="#8b949e" strokeWidth="1.5" />
      <path d="M5 10l9 6 9-6" stroke="#8b949e" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
