import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAuditStreamConfig, updateHecToken } from '../../api/auditStream';
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
/*  HEC Token form                                                     */
/* ------------------------------------------------------------------ */

function HecTokenForm() {
  const queryClient = useQueryClient();
  const [successMsg, setSuccessMsg] = useState('');
  const [generatedToken, setGeneratedToken] = useState('');

  const mutation = useMutation({
    mutationFn: updateHecToken,
    onSuccess: (data) => {
      setSuccessMsg(data.message || 'HEC token saved.');
      setGeneratedToken(data.hec_token);
      void queryClient.invalidateQueries({ queryKey: ['audit-stream-config'] });
      setTimeout(() => setSuccessMsg(''), 6000);
    },
  });

  const handleGenerate = () => {
    mutation.mutate({ hec_token: '' }); // empty = auto-generate
  };

  return (
    <div className={styles.editForm}>
      <p className={styles.formHint}>
        Generate a token to use in GitHub&apos;s Splunk streaming configuration.
      </p>

      {mutation.isError && (
        <ErrorBanner
          message={
            mutation.error instanceof Error ? mutation.error.message : 'Failed to save HEC token.'
          }
        />
      )}

      {successMsg && <div className={styles.successBanner}>{successMsg}</div>}

      {generatedToken && (
        <div className={styles.configRow}>
          <span className={styles.configLabel}>HEC Token</span>
          <span className={styles.configValue}>
            <code>{generatedToken}</code>
            <CopyButton text={generatedToken} />
          </span>
        </div>
      )}

      <div className={styles.formActions}>
        <Button
          type="button"
          variant="primary"
          onClick={handleGenerate}
          disabled={mutation.isPending}
        >
          {mutation.isPending ? 'Generating…' : 'Generate HEC Token'}
        </Button>
      </div>
    </div>
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
        {/* Splunk HEC connection details */}
        <div className={styles.configGrid}>
          <ConfigRow label="HEC URL" value={config.hec_endpoint} copyable />
        </div>

        {/* HEC Instructions */}
        <InstructionsList instructions={config.hec_instructions} />

        {/* Generate HEC token */}
        <div className={styles.auditStreamCredentials}>
          <h4 className={styles.configSectionTitle}>HEC Token</h4>
          <HecTokenForm />
        </div>
      </div>
    </Card>
  );
}
