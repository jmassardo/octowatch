import { useState, useCallback, useEffect } from 'react';
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
import { Button } from '../../components/primitives/Button';
import { Spinner } from '../../components/primitives/Spinner';
import styles from './Setup.module.css';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const STEP_LABELS = ['Authenticate', 'GitHub OAuth', 'GitHub App', 'TLS', 'Review'];
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

function TokenLoginStep({
  onComplete,
}: {
  onComplete: () => void;
}) {
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
          <code className={styles.hintCode}>docker compose logs api | grep &quot;Setup token&quot;</code>
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
        Skipping OAuth means users won&apos;t be able to sign in with GitHub until it&apos;s configured later.
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
        <p className={styles.hint}>The slug from your GitHub Enterprise URL (e.g., github.com/enterprises/my-enterprise).</p>
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
        Skipping the GitHub App means audit log sync and advanced features won&apos;t be available until configured.
      </p>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 4: TLS                                                        */
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
        Skipping TLS will keep the existing self-signed certificate. You can update it later in settings.
      </p>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Step 5: Review & Complete                                          */
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
    { label: 'TLS Certificate', key: 'tls' },
  ];

  if (done) {
    return (
      <div className={styles.completeBanner}>
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="10" stroke="var(--success)" strokeWidth="2" />
          <path d="M8 12l3 3 5-5" stroke="var(--success)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
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
              {completedSteps[item.key] ? (
                <span className={styles.reviewConfigured}>✓ Configured</span>
              ) : (
                <span className={styles.reviewSkipped}>Skipped</span>
              )}
            </span>
          </div>
        ))}
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
        return <GitHubOAuthStep onComplete={handleOAuthComplete} onBack={goBack} onSkip={handleOAuthSkip} />;
      case 2:
        return <GitHubAppStep onComplete={handleAppComplete} onBack={goBack} onSkip={handleAppSkip} />;
      case 3:
        return <TLSStep onComplete={handleTLSComplete} onBack={goBack} onSkip={handleTLSSkip} />;
      case 4:
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
              <circle cx="12" cy="12" r="3.5" fill="#bc8cff" />
              <ellipse cx="12" cy="12" rx="9" ry="5.5" stroke="#bc8cff" strokeWidth="1.5" fill="none" />
              <line x1="12" y1="2" x2="12" y2="5" stroke="#bc8cff" strokeWidth="1.5" strokeLinecap="round" />
              <line x1="12" y1="19" x2="12" y2="22" stroke="#bc8cff" strokeWidth="1.5" strokeLinecap="round" />
              <line x1="2" y1="12" x2="5" y2="12" stroke="#bc8cff" strokeWidth="1.5" strokeLinecap="round" />
              <line x1="19" y1="12" x2="22" y2="12" stroke="#bc8cff" strokeWidth="1.5" strokeLinecap="round" />
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
