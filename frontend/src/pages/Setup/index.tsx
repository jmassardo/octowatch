import { useState, useEffect, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  setupLogin,
  setupGitHubOAuth,
  setupGitHubApp,
  setupTLS,
  completeSetup,
} from '../../api/setup';
import type {
  SetupLoginRequest,
  GitHubOAuthSetup,
  GitHubAppSetup,
  TLSSetup,
} from '../../api/setup';
import { triggerSync, getSyncStatus } from '../../api/sync';
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import styles from './Setup.module.css';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const STEP_LABELS = ['Authenticate', 'GitHub OAuth', 'GitHub App', 'Initial Sync', 'TLS', 'Review'];
const TOTAL_STEPS = STEP_LABELS.length;

/* ------------------------------------------------------------------ */
/*  Shared helpers                                                     */
/* ------------------------------------------------------------------ */

function StepError({ message }: { message: string | null }) {
  if (!message) return null;
  return <p className={styles.errorMessage}>{message}</p>;
}

/* ------------------------------------------------------------------ */
/*  Step 1: Token Login                                                */
/* ------------------------------------------------------------------ */

function TokenLoginStep({ onComplete }: { onComplete: () => void }) {
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!token.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const req: SetupLoginRequest = { token: token.trim() };
      await setupLogin(req);
      onComplete();
    } catch {
      setError('Invalid setup token. Please check the token and try again.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className={styles.formGroup}>
        <label className={styles.label} htmlFor="setup-token">
          Setup Token
        </label>
        <input
          id="setup-token"
          className={styles.input}
          type="password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="Enter your setup token"
          autoFocus
          required
          disabled={loading}
        />
        <p className={styles.hint}>
          Find your setup token in the container logs:{' '}
          <code className={styles.hintCode}>
            docker compose logs api | grep &quot;Setup token&quot;
          </code>
        </p>
      </div>
      <StepError message={error} />
      <div className={styles.actions}>
        <span />
        <Button variant="primary" type="submit" disabled={loading || !token.trim()}>
          {loading ? <Spinner size={14} /> : 'Authenticate'}
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 2: GitHub OAuth                                               */
/* ------------------------------------------------------------------ */

function GitHubOAuthStep({
  onComplete,
  onBack,
  onSkip,
}: {
  onComplete: () => void;
  onBack: () => void;
  onSkip: () => void;
}) {
  const [clientId, setClientId] = useState('');
  const [clientSecret, setClientSecret] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!clientId.trim() || !clientSecret.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const req: GitHubOAuthSetup = {
        client_id: clientId.trim(),
        client_secret: clientSecret.trim(),
      };
      await setupGitHubOAuth(req);
      onComplete();
    } catch {
      setError('Failed to configure GitHub OAuth. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className={styles.formGroup}>
        <label className={styles.label} htmlFor="oauth-client-id">
          Client ID
        </label>
        <input
          id="oauth-client-id"
          className={styles.input}
          type="text"
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
          placeholder="Ov23li..."
          disabled={loading}
        />
      </div>
      <div className={styles.formGroup}>
        <label className={styles.label} htmlFor="oauth-client-secret">
          Client Secret
        </label>
        <input
          id="oauth-client-secret"
          className={styles.input}
          type="password"
          value={clientSecret}
          onChange={(e) => setClientSecret(e.target.value)}
          placeholder="Enter client secret"
          disabled={loading}
        />
      </div>
      <p className={styles.hint}>
        Create a GitHub OAuth App at{' '}
        <a href="https://github.com/settings/developers" target="_blank" rel="noopener noreferrer">
          github.com/settings/developers
        </a>
      </p>
      <StepError message={error} />
      <div className={styles.actions}>
        <Button type="button" onClick={onBack} disabled={loading}>
          Back
        </Button>
        <div className={styles.actionsRight}>
          <Button type="button" onClick={onSkip} disabled={loading}>
            Skip
          </Button>
          <Button
            variant="primary"
            type="submit"
            disabled={loading || !clientId.trim() || !clientSecret.trim()}
          >
            {loading ? <Spinner size={14} /> : 'Next'}
          </Button>
        </div>
      </div>
      <p className={styles.skipNote}>
        Skipping OAuth means users won&apos;t be able to sign in with GitHub until it&apos;s
        configured later.
      </p>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 3: GitHub App                                                 */
/* ------------------------------------------------------------------ */

function GitHubAppStep({
  onComplete,
  onBack,
  onSkip,
}: {
  onComplete: () => void;
  onBack: () => void;
  onSkip: () => void;
}) {
  const [appId, setAppId] = useState('');
  const [privateKey, setPrivateKey] = useState('');
  const [enterpriseSlug, setEnterpriseSlug] = useState('');
  const [syncEnabled, setSyncEnabled] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!appId.trim() || !privateKey.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const req: GitHubAppSetup = {
        app_id: appId.trim(),
        private_key_pem: privateKey.trim(),
        enterprise_slug: enterpriseSlug.trim(),
        sync_enabled: syncEnabled,
        sync_interval_days: 60,
        sync_orgs: '',
      };
      await setupGitHubApp(req);
      onComplete();
    } catch {
      setError('Failed to configure GitHub App. Please verify your App ID and private key.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className={styles.formGroup}>
        <label className={styles.label} htmlFor="app-id">
          App ID
        </label>
        <input
          id="app-id"
          className={styles.input}
          type="text"
          value={appId}
          onChange={(e) => setAppId(e.target.value)}
          placeholder="123456"
          disabled={loading}
        />
      </div>
      <div className={styles.formGroup}>
        <label className={styles.label} htmlFor="private-key">
          Private Key (PEM)
        </label>
        <textarea
          id="private-key"
          className={styles.textarea}
          value={privateKey}
          onChange={(e) => setPrivateKey(e.target.value)}
          placeholder="-----BEGIN RSA PRIVATE KEY-----&#10;..."
          disabled={loading}
        />
        <p className={styles.hint}>Paste the contents of your GitHub App private key PEM file.</p>
      </div>
      <div className={styles.formGroup}>
        <label className={styles.label} htmlFor="enterprise-slug">
          Enterprise Slug
        </label>
        <input
          id="enterprise-slug"
          className={styles.input}
          type="text"
          value={enterpriseSlug}
          onChange={(e) => setEnterpriseSlug(e.target.value)}
          placeholder="my-enterprise"
          disabled={loading}
        />
        <p className={styles.hint}>
          The slug from your GitHub Enterprise URL (e.g., github.com/enterprises/my-enterprise).
        </p>
      </div>
      <div className={styles.checkboxRow}>
        <input
          id="sync-enabled"
          type="checkbox"
          checked={syncEnabled}
          onChange={(e) => setSyncEnabled(e.target.checked)}
          disabled={loading}
        />
        <label className={styles.checkboxLabel} htmlFor="sync-enabled">
          Enable automatic data sync
        </label>
      </div>
      <StepError message={error} />
      <div className={styles.actions}>
        <Button type="button" onClick={onBack} disabled={loading}>
          Back
        </Button>
        <div className={styles.actionsRight}>
          <Button type="button" onClick={onSkip} disabled={loading}>
            Skip
          </Button>
          <Button
            variant="primary"
            type="submit"
            disabled={loading || !appId.trim() || !privateKey.trim()}
          >
            {loading ? <Spinner size={14} /> : 'Next'}
          </Button>
        </div>
      </div>
      <p className={styles.skipNote}>
        Skipping the GitHub App means audit log sync and advanced features won&apos;t be available
        until configured.
      </p>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 4: Initial Sync                                               */
/* ------------------------------------------------------------------ */

type SyncPhase = 'idle' | 'syncing' | 'completed' | 'failed';

function InitialSyncStep({
  onComplete,
  onBack,
  onSkip,
  appConfigured,
}: {
  onComplete: () => void;
  onBack: () => void;
  onSkip: () => void;
  appConfigured: boolean;
}) {
  const [phase, setPhase] = useState<SyncPhase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);

  const { data: syncStatus } = useQuery({
    queryKey: ['setup-sync-status'],
    queryFn: async () => {
      const status = await getSyncStatus();
      // Transition phase inside queryFn callback to avoid setState-in-effect
      if (status?.status === 'completed') {
        setPolling(false);
        setPhase('completed');
      } else if (status?.status === 'failed') {
        setPolling(false);
        setPhase('failed');
        setError(status?.error_message ?? 'Sync failed. Please try again.');
      }
      return status;
    },
    enabled: polling,
    refetchInterval: polling ? 5000 : false,
    staleTime: 0,
  });

  // Derive entityProgress from query data (no setState needed)
  const entityProgress = syncStatus?.entity_counts
    ? Object.entries(syncStatus.entity_counts)
        .map(([entity, count]) => `${entity}: ${count}`)
        .join(', ')
    : null;

  async function handleStartSync() {
    setPhase('syncing');
    setError(null);
    try {
      await triggerSync('full');
      setPolling(true);
    } catch {
      setPhase('failed');
      setError('Failed to start sync. Please try again.');
    }
  }

  if (!appConfigured) {
    return (
      <div>
        <p className={styles.hint}>Configure a GitHub App first to enable enterprise sync.</p>
        <div className={styles.actions}>
          <Button type="button" onClick={onBack}>
            Back
          </Button>
          <Button type="button" onClick={onSkip}>
            Skip
          </Button>
        </div>
      </div>
    );
  }

  if (phase === 'completed') {
    return (
      <div>
        <p className={styles.syncSuccess}>✓ Sync complete!</p>
        {entityProgress && <p className={styles.hint}>{entityProgress}</p>}
        <div className={styles.actions}>
          <Button type="button" onClick={onBack}>
            Back
          </Button>
          <Button variant="primary" onClick={onComplete}>
            Continue
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2 className={styles.syncHeading}>Initial Enterprise Sync</h2>
      <p className={styles.syncDescription}>
        Sync your GitHub enterprise metadata (organizations, repositories, members, teams) to
        establish a baseline for security monitoring.
      </p>
      <p className={styles.hint}>
        Audit log events can be imported separately via S3/MinIO file export.
      </p>
      {phase === 'syncing' && (
        <div className={styles.syncProgress}>
          <Spinner size={16} />
          <span>Syncing…{entityProgress ? ` (${entityProgress})` : ''}</span>
        </div>
      )}
      <StepError message={error} />
      <div className={styles.actions}>
        <Button type="button" onClick={onBack} disabled={phase === 'syncing'}>
          Back
        </Button>
        <div className={styles.actionsRight}>
          <Button type="button" onClick={onSkip} disabled={phase === 'syncing'}>
            Skip
          </Button>
          {phase === 'syncing' ? (
            <Button variant="primary" onClick={onComplete}>
              Continue — sync runs in background
            </Button>
          ) : phase === 'failed' ? (
            <Button variant="primary" onClick={handleStartSync}>
              Retry
            </Button>
          ) : (
            <Button variant="primary" onClick={handleStartSync}>
              Start Sync
            </Button>
          )}
        </div>
      </div>
      <p className={styles.skipNote}>
        You can skip this step and run the sync later from the admin settings.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 5: TLS                                                        */
/* ------------------------------------------------------------------ */

function TLSStep({
  onComplete,
  onBack,
  onSkip,
}: {
  onComplete: () => void;
  onBack: () => void;
  onSkip: () => void;
}) {
  const [certPem, setCertPem] = useState('');
  const [keyPem, setKeyPem] = useState('');
  const [generateSelfSigned, setGenerateSelfSigned] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!generateSelfSigned && (!certPem.trim() || !keyPem.trim())) return;
    setLoading(true);
    setError(null);
    try {
      const req: TLSSetup = {
        cert_pem: generateSelfSigned ? '' : certPem.trim(),
        key_pem: generateSelfSigned ? '' : keyPem.trim(),
        generate_self_signed: generateSelfSigned,
      };
      await setupTLS(req);
      onComplete();
    } catch {
      setError('Failed to configure TLS. Please check your certificate and key.');
    } finally {
      setLoading(false);
    }
  }

  const canSubmit = generateSelfSigned || (certPem.trim() && keyPem.trim());

  return (
    <form onSubmit={handleSubmit}>
      <div className={styles.checkboxRow}>
        <input
          id="self-signed"
          type="checkbox"
          checked={generateSelfSigned}
          onChange={(e) => setGenerateSelfSigned(e.target.checked)}
          disabled={loading}
        />
        <label className={styles.checkboxLabel} htmlFor="self-signed">
          Generate self-signed certificate
        </label>
      </div>

      {!generateSelfSigned && (
        <>
          <div className={styles.formGroup}>
            <label className={styles.label} htmlFor="cert-pem">
              Certificate (PEM)
            </label>
            <textarea
              id="cert-pem"
              className={styles.textarea}
              value={certPem}
              onChange={(e) => setCertPem(e.target.value)}
              placeholder="-----BEGIN CERTIFICATE-----&#10;..."
              disabled={loading}
            />
          </div>
          <div className={styles.formGroup}>
            <label className={styles.label} htmlFor="key-pem">
              Private Key (PEM)
            </label>
            <textarea
              id="key-pem"
              className={styles.textarea}
              value={keyPem}
              onChange={(e) => setKeyPem(e.target.value)}
              placeholder="-----BEGIN PRIVATE KEY-----&#10;..."
              disabled={loading}
            />
          </div>
        </>
      )}

      <StepError message={error} />
      <div className={styles.actions}>
        <Button type="button" onClick={onBack} disabled={loading}>
          Back
        </Button>
        <div className={styles.actionsRight}>
          <Button type="button" onClick={onSkip} disabled={loading}>
            Skip
          </Button>
          <Button variant="primary" type="submit" disabled={loading || !canSubmit}>
            {loading ? <Spinner size={14} /> : 'Next'}
          </Button>
        </div>
      </div>
      <p className={styles.skipNote}>
        Skipping TLS will keep the existing self-signed certificate. You can update it later in
        settings.
      </p>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 6: Review & Complete                                          */
/* ------------------------------------------------------------------ */

function ReviewStep({
  completedSteps,
  onBack,
}: {
  completedSteps: Record<string, boolean>;
  onBack: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const navigate = useNavigate();

  const isTerminal = (s: string) => s === 'completed' || s === 'failed';

  const { data: syncStatusData } = useQuery({
    queryKey: ['setup-sync-status'],
    queryFn: getSyncStatus,
    enabled: !!completedSteps.sync,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && isTerminal(status)) return false;
      return 5000;
    },
  });

  const syncStatus = useMemo(() => {
    if (!completedSteps.sync || !syncStatusData) return null;
    if (syncStatusData.status === 'completed') return 'completed';
    if (syncStatusData.status === 'failed') return 'failed';
    return 'running';
  }, [completedSteps.sync, syncStatusData]);

  useEffect(() => {
    if (!done) return;
    const timer = setTimeout(() => navigate('/login', { replace: true }), 3000);
    return () => clearTimeout(timer);
  }, [done, navigate]);

  async function handleComplete() {
    setLoading(true);
    setError(null);
    try {
      await completeSetup();
      setDone(true);
    } catch {
      setError('Failed to complete setup. Please try again.');
    } finally {
      setLoading(false);
    }
  }

  const items: { label: string; key: string }[] = [
    { label: 'Authentication', key: 'token' },
    { label: 'GitHub OAuth', key: 'oauth' },
    { label: 'GitHub App', key: 'app' },
    { label: 'Initial Sync', key: 'sync' },
    { label: 'TLS Certificate', key: 'tls' },
  ];

  if (done) {
    return (
      <div className={styles.completeBanner}>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="var(--success)" strokeWidth="2" />
          <path
            d="M8 12l3 3 5-5"
            stroke="var(--success)"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <h2 className={styles.completeTitle}>Setup Complete!</h2>
        <p className={styles.completeSubtitle}>Redirecting to login page in a few seconds…</p>
      </div>
    );
  }

  return (
    <div>
      <div>
        {items.map((item) => (
          <div key={item.key} className={styles.reviewItem}>
            <span className={styles.reviewLabel}>{item.label}</span>
            <span className={styles.reviewValue}>
              {item.key === 'sync' ? (
                !completedSteps.sync ? (
                  <span className={styles.reviewSkipped}>Skipped</span>
                ) : syncStatus === 'completed' ? (
                  <span className={styles.reviewConfigured}>✓ Sync completed</span>
                ) : syncStatus === 'failed' ? (
                  <span className={styles.reviewSkipped}>✗ Sync failed</span>
                ) : syncStatus === 'running' ? (
                  <span className={styles.reviewConfigured}>⏳ Sync in progress</span>
                ) : (
                  <span className={styles.reviewConfigured}>✓ Sync started</span>
                )
              ) : completedSteps[item.key] ? (
                <span className={styles.reviewConfigured}>✓ Configured</span>
              ) : (
                <span className={styles.reviewSkipped}>Skipped</span>
              )}
            </span>
          </div>
        ))}
        {completedSteps.sync && syncStatus === 'running' && (
          <p className={styles.hint}>
            Sync will continue in the background. Check Admin → Sync for progress.
          </p>
        )}
      </div>
      <StepError message={error} />
      <div className={styles.actions}>
        <Button type="button" onClick={onBack} disabled={loading}>
          Back
        </Button>
        <Button variant="primary" onClick={handleComplete} disabled={loading}>
          {loading ? <Spinner size={14} /> : 'Complete Setup'}
        </Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main Setup Wizard                                                  */
/* ------------------------------------------------------------------ */

export function SetupPage() {
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Record<string, boolean>>({
    token: false,
    oauth: false,
    app: false,
    sync: false,
    tls: false,
  });

  const markComplete = useCallback((key: string) => {
    setCompletedSteps((prev) => ({ ...prev, [key]: true }));
  }, []);

  const goNext = useCallback(() => {
    setCurrentStep((s) => Math.min(s + 1, TOTAL_STEPS - 1));
  }, []);

  const goBack = useCallback(() => {
    setCurrentStep((s) => Math.max(s - 1, 0));
  }, []);

  function handleTokenComplete() {
    markComplete('token');
    goNext();
  }

  function handleOAuthComplete() {
    markComplete('oauth');
    goNext();
  }

  function handleOAuthSkip() {
    goNext();
  }

  function handleAppComplete() {
    markComplete('app');
    goNext();
  }

  function handleAppSkip() {
    goNext();
  }

  function handleSyncComplete() {
    markComplete('sync');
    goNext();
  }

  function handleSyncSkip() {
    goNext();
  }

  function handleTLSComplete() {
    markComplete('tls');
    goNext();
  }

  function handleTLSSkip() {
    goNext();
  }

  function renderStep() {
    switch (currentStep) {
      case 0:
        return <TokenLoginStep onComplete={handleTokenComplete} />;
      case 1:
        return (
          <GitHubOAuthStep
            onComplete={handleOAuthComplete}
            onBack={goBack}
            onSkip={handleOAuthSkip}
          />
        );
      case 2:
        return (
          <GitHubAppStep onComplete={handleAppComplete} onBack={goBack} onSkip={handleAppSkip} />
        );
      case 3:
        return (
          <InitialSyncStep
            onComplete={handleSyncComplete}
            onBack={goBack}
            onSkip={handleSyncSkip}
            appConfigured={completedSteps['app'] === true}
          />
        );
      case 4:
        return <TLSStep onComplete={handleTLSComplete} onBack={goBack} onSkip={handleTLSSkip} />;
      case 5:
        return <ReviewStep completedSteps={completedSteps} onBack={goBack} />;
      default:
        return null;
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.wizardCard}>
        <div className={styles.header}>
          <div className={styles.logo}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="3.5" fill="var(--done)" />
              <ellipse
                cx="12"
                cy="12"
                rx="9"
                ry="5.5"
                stroke="var(--done)"
                strokeWidth="1.5"
                fill="none"
              />
              <line
                x1="12"
                y1="2"
                x2="12"
                y2="5"
                stroke="var(--done)"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
              <line
                x1="12"
                y1="19"
                x2="12"
                y2="22"
                stroke="var(--done)"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
              <line
                x1="2"
                y1="12"
                x2="5"
                y2="12"
                stroke="var(--done)"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
              <line
                x1="19"
                y1="12"
                x2="22"
                y2="12"
                stroke="var(--done)"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <h1 className={styles.title}>OctoWatch Setup</h1>
          <p className={styles.subtitle}>Configure your instance to get started</p>
        </div>

        {/* Stepper */}
        <div className={styles.stepper}>
          {STEP_LABELS.map((_, i) => {
            let cls = styles.stepPending;
            if (i < currentStep) cls = styles.stepComplete;
            else if (i === currentStep) cls = styles.stepActive;
            return <div key={i} className={cls} />;
          })}
        </div>

        <p className={styles.stepLabel}>
          Step {currentStep + 1} of {TOTAL_STEPS}: {STEP_LABELS[currentStep]}
        </p>

        {renderStep()}
      </div>
    </div>
  );
}
