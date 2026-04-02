import { useRef, useState, useCallback } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { uploadFile, getIngestJob, listIngestJobs } from '../../api/ingest';
import { Card, CardHeader } from '../../components/primitives/Card';
import { Label } from '../../components/primitives/Label';
import { Spinner } from '../../components/primitives/Spinner';
import { ErrorBanner } from '../../components/primitives/ErrorBanner';
import type { ManualIngestJob, IngestType, IngestJobStatus } from '../../types/ingest';
import { formatShortDateTime } from '../../utils/dates';
import styles from './Integrations.module.css';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const MAX_FILE_SIZE = 500 * 1024 * 1024; // 500 MB

interface IngestCardConfig {
  type: IngestType;
  title: string;
  description: string;
  accept: string;
  formatHint: string;
}

const INGEST_CARDS: IngestCardConfig[] = [
  {
    type: 'audit_log',
    title: 'Audit Log',
    description: 'Import GitHub Enterprise audit log exports for security analysis.',
    accept: '.csv,.json,.json.gz,.ndjson',
    formatHint: 'Accepts .csv, .json, .ndjson · max 500 MB',
  },
  {
    type: 'audit_log_git',
    title: 'Audit Log (Git)',
    description: 'Import Git-related audit log events separately for detailed analysis.',
    accept: '.csv,.json,.json.gz,.ndjson',
    formatHint: 'Accepts .csv, .json, .ndjson · max 500 MB',
  },
  {
    type: 'copilot_usage',
    title: 'Copilot Usage',
    description: 'Import Copilot usage metrics from the GitHub Copilot Metrics API.',
    accept: '.json',
    formatHint: 'Accepts .json · Copilot Metrics API format · max 500 MB',
  },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function statusVariant(status: IngestJobStatus): 'success' | 'danger' | 'attention' | 'muted' {
  switch (status) {
    case 'completed':
      return 'success';
    case 'failed':
      return 'danger';
    case 'running':
      return 'attention';
    default:
      return 'muted';
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const TERMINAL_STATUSES = new Set<IngestJobStatus>(['completed', 'failed']);

/* ------------------------------------------------------------------ */
/*  Upload icon                                                        */
/* ------------------------------------------------------------------ */

function UploadIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 16V4m0 0l-4 4m4-4l4 4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/*  Single upload card                                                 */
/* ------------------------------------------------------------------ */

function IngestUploadCard({ config }: { config: IngestCardConfig }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // Poll active job status
  const { data: activeJob } = useQuery({
    queryKey: ['ingest-job', activeJobId],
    queryFn: () => getIngestJob(activeJobId!),
    enabled: activeJobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status && TERMINAL_STATUSES.has(status)) return false;
      return 3000;
    },
  });

  // Clear active job when terminal
  if (activeJob && TERMINAL_STATUSES.has(activeJob.status) && activeJobId) {
    // Schedule clearing so it's not during render
    setTimeout(() => {
      setActiveJobId(null);
      queryClient.invalidateQueries({ queryKey: ['ingest-jobs'] });
    }, 5000);
  }

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadFile(file, config.type),
    onSuccess: (job) => {
      setError(null);
      setActiveJobId(job.id);
    },
    onError: (err: Error) => {
      setError(err.message);
    },
  });

  const handleFile = useCallback(
    (file: File) => {
      setError(null);
      if (file.size > MAX_FILE_SIZE) {
        setError(`File exceeds 500 MB limit (${formatFileSize(file.size)})`);
        return;
      }
      uploadMutation.mutate(file);
    },
    [uploadMutation],
  );

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function handleDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(true);
  }

  function handleDragLeave() {
    setDragOver(false);
  }

  const isUploading = uploadMutation.isPending;
  const isProcessing = activeJob && !TERMINAL_STATUSES.has(activeJob.status);

  return (
    <div className={styles.ingestCard} data-testid={`ingest-card-${config.type}`}>
      <div className={styles.ingestCardHeader}>
        <h4 className={styles.ingestCardTitle}>{config.title}</h4>
        <p className={styles.ingestCardDesc}>{config.description}</p>
      </div>

      <div
        className={`${styles.ingestDrop} ${dragOver ? styles.ingestDropActive : ''}`}
        onClick={() => inputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        role="button"
        tabIndex={0}
        aria-label={`Upload ${config.title}`}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
      >
        {isUploading ? (
          <div className={styles.ingestUploading}>
            <Spinner size={24} />
            <p>Uploading…</p>
          </div>
        ) : (
          <>
            <div className={styles.ingestDropIcon}>
              <UploadIcon />
            </div>
            <p className={styles.ingestDropText}>Drop file here or browse</p>
            <p className={styles.ingestDropHint}>{config.formatHint}</p>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={config.accept}
          className={styles.hiddenInput}
          aria-hidden="true"
          tabIndex={-1}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFile(file);
            e.target.value = '';
          }}
        />
      </div>

      {error && <ErrorBanner message={error} onRetry={() => setError(null)} />}

      {/* Active job progress */}
      {activeJob && (
        <div className={styles.ingestJobProgress} data-testid="ingest-job-progress">
          <div className={styles.ingestJobRow}>
            <span className={styles.ingestJobFile}>{activeJob.original_filename}</span>
            <Label variant={statusVariant(activeJob.status)}>{activeJob.status}</Label>
          </div>
          <div className={styles.ingestJobStats}>
            {isProcessing && <Spinner size={14} />}
            <span>{activeJob.rows_processed.toLocaleString()} rows processed</span>
            {activeJob.rows_skipped > 0 && (
              <span className={styles.ingestJobWarn}>{activeJob.rows_skipped} skipped</span>
            )}
            {activeJob.rows_failed > 0 && (
              <span className={styles.ingestJobError}>{activeJob.rows_failed} failed</span>
            )}
          </div>
          {activeJob.error_details && (
            <p className={styles.ingestJobErrorDetail}>{activeJob.error_details}</p>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Job history table                                                  */
/* ------------------------------------------------------------------ */

function IngestJobHistory() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['ingest-jobs'],
    queryFn: () => listIngestJobs(1),
  });

  if (isLoading) {
    return (
      <div className={styles.syncLoading}>
        <Spinner />
        <span>Loading job history…</span>
      </div>
    );
  }

  if (isError) {
    return <ErrorBanner message="Failed to load ingest jobs" onRetry={() => refetch()} />;
  }

  const jobs = data?.items ?? [];

  if (jobs.length === 0) {
    return <p className={styles.emptyText}>No import jobs yet</p>;
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.historyTable} data-testid="ingest-history-table">
        <thead>
          <tr>
            <th>File</th>
            <th>Type</th>
            <th>Size</th>
            <th>Submitted</th>
            <th>Records</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job: ManualIngestJob) => (
            <tr key={job.id}>
              <td className={styles.cellTruncate}>{job.original_filename}</td>
              <td>{job.ingest_type.replace(/_/g, ' ')}</td>
              <td>{formatFileSize(job.file_size_bytes)}</td>
              <td>{formatShortDateTime(job.created_at)}</td>
              <td>{job.rows_processed > 0 ? job.rows_processed.toLocaleString() : '—'}</td>
              <td>
                <Label variant={statusVariant(job.status)}>{job.status}</Label>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  ManualIngestPanel component                                        */
/* ------------------------------------------------------------------ */

export function ManualIngestPanel() {
  return (
    <Card data-testid="manual-ingest-panel">
      <CardHeader>Import Data Files</CardHeader>
      <p className={styles.ingestIntro}>
        Upload exported data files to analyze without live API access — great for evaluating
        OctoWatch or filling historical gaps.
      </p>
      <div className={styles.ingestGrid}>
        {INGEST_CARDS.map((config) => (
          <IngestUploadCard key={config.type} config={config} />
        ))}
      </div>

      <div className={styles.ingestHistorySection}>
        <h4 className={styles.ingestHistoryTitle}>Import History</h4>
        <IngestJobHistory />
      </div>
    </Card>
  );
}
