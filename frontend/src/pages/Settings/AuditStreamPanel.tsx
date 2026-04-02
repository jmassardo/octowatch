import { useState, useCallback, type FormEvent } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAuditStreamConfig, updateAuditStreamConfig } from '../../api/auditStream';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Button } from '../../components/primitives/Button';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import styles from './Settings.module.css';

/* ------------------------------------------------------------------ */
/*  Copy-to-clipboard helper                                           */
/* ------------------------------------------------------------------ */

function CopyButton({ text }: { text: string }) {
  const [label, setLabel] = useState('Copy');

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setLabel('Copied!');
      setTimeout(() => setLabel('Copy'), 1500);
    } catch {
      /* clipboard API may be unavailable */
    }
  }, [text]);

  return (
    <button type="button" className={styles.copyBtn} onClick={handleCopy}>
      {label}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/*  Config detail row                                                  */
/* ------------------------------------------------------------------ */

function ConfigRow({
  label,
  value,
  copyable,
}: {
  label: string;
  value: string;
  copyable?: boolean;
}) {
  return (
    <div className={styles.configRow}>
      <span className={styles.configLabel}>{label}</span>
      <span className={styles.configValue}>
        <code>{value}</code>
        {copyable && <CopyButton text={value} />}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Instructions section                                               */
/* ------------------------------------------------------------------ */

function InstructionsList({ instructions }: { instructions: Record<string, string> }) {
  const [expanded, setExpanded] = useState(false);

  const sortedSteps = Object.entries(instructions).sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className={styles.instructionsSection}>
      <button
        type="button"
        className={styles.instructionsToggle}
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <span className={styles.instructionsChevron} data-expanded={expanded}>
          ▶
        </span>
        Setup Instructions
      </button>

      {expanded && (
        <div className={styles.instructionsBody}>
          <p className={styles.instructionsNote}>
            Configure these settings in your GitHub Enterprise instance under{' '}
            <strong>Settings → Audit Log → Log Streaming</strong>.
          </p>
          <ol className={styles.instructionSteps}>
            {sortedSteps.map(([key, step]) => (
              <li key={key} className={styles.instructionStep}>
                {step}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Credentials form                                                   */
/* ------------------------------------------------------------------ */

function CredentialsForm({ currentUser }: { currentUser: string }) {
  const queryClient = useQueryClient();
  const [streamUser, setStreamUser] = useState(currentUser);
  const [streamPassword, setStreamPassword] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const mutation = useMutation({
    mutationFn: updateAuditStreamConfig,
    onSuccess: (data) => {
      setSuccessMsg(data.message || 'Credentials updated successfully.');
      setStreamPassword('');
      void queryClient.invalidateQueries({ queryKey: ['audit-stream-config'] });
      setTimeout(() => setSuccessMsg(''), 4000);
    },
  });

  const passwordValid = streamPassword.length >= 8;
  const formValid = streamUser.trim().length > 0 && passwordValid;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!formValid) return;
    mutation.mutate({ stream_user: streamUser.trim(), stream_password: streamPassword });
  };

  return (
    <form className={styles.editForm} onSubmit={handleSubmit}>
      <div className={styles.formRow}>
        <label className={styles.formLabel} htmlFor="audit-stream-user">
          Access Key ID
        </label>
        <input
          id="audit-stream-user"
          className={styles.formInput}
          type="text"
          value={streamUser}
          onChange={(e) => setStreamUser(e.target.value)}
          required
          autoComplete="username"
        />
      </div>

      <div className={styles.formRow}>
        <label className={styles.formLabel} htmlFor="audit-stream-password">
          Secret Access Key
        </label>
        <input
          id="audit-stream-password"
          className={styles.formInput}
          type="password"
          value={streamPassword}
          onChange={(e) => setStreamPassword(e.target.value)}
          required
          minLength={8}
          placeholder="Enter new secret access key"
          autoComplete="new-password"
        />
        {streamPassword.length > 0 && !passwordValid && (
          <span className={styles.formHint} style={{ color: 'var(--danger)' }}>
            Must be at least 8 characters.
          </span>
        )}
      </div>

      {mutation.isError && (
        <ErrorBanner
          message={
            mutation.error instanceof Error
              ? mutation.error.message
              : 'Failed to update credentials.'
          }
        />
      )}

      {successMsg && <div className={styles.successBanner}>{successMsg}</div>}

      <div className={styles.formActions}>
        <Button type="submit" variant="primary" disabled={!formValid || mutation.isPending}>
          {mutation.isPending ? 'Saving…' : 'Save Credentials'}
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/*  Main panel                                                         */
/* ------------------------------------------------------------------ */

export function AuditStreamPanel() {
  const {
    data: config,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['audit-stream-config'],
    queryFn: getAuditStreamConfig,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>Audit Log Streaming</CardHeader>
        <div style={{ padding: '2rem', textAlign: 'center' }}>
          <Spinner size={24} />
        </div>
      </Card>
    );
  }

  if (isError) {
    return (
      <Card>
        <CardHeader>Audit Log Streaming</CardHeader>
        <div style={{ padding: '1rem' }}>
          <ErrorBanner
            message={error instanceof Error ? error.message : 'Failed to load streaming config.'}
            onRetry={() => void refetch()}
          />
        </div>
      </Card>
    );
  }

  if (!config) return null;

  return (
    <Card>
      <CardHeader
        actions={
          <Label variant={config.configured ? 'success' : 'attention'}>
            {config.configured ? 'Configured' : 'Not configured'}
          </Label>
        }
      >
        Audit Log Streaming
      </CardHeader>

      <div className={styles.auditStreamBody}>
        {/* Connection details */}
        <div className={styles.configGrid}>
          <ConfigRow label="S3 Endpoint" value={config.s3_endpoint} copyable />
          <ConfigRow label="Bucket" value={config.bucket} copyable />
          <ConfigRow label="Access Key ID" value={config.stream_user} copyable />
          <ConfigRow label="Region" value={config.region} copyable />
        </div>

        {/* Instructions */}
        <InstructionsList instructions={config.instructions} />

        {/* Update credentials */}
        <div className={styles.auditStreamCredentials}>
          <h4 className={styles.configSectionTitle}>Update Credentials</h4>
          <CredentialsForm currentUser={config.stream_user} />
        </div>
      </div>
    </Card>
  );
}
