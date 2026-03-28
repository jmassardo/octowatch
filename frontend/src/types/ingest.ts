export type IngestType = 'audit_log' | 'audit_log_git' | 'copilot_usage';
export type IngestJobStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface ManualIngestJob {
  readonly id: string;
  readonly ingest_type: IngestType;
  readonly status: IngestJobStatus;
  readonly submitted_by: string;
  readonly original_filename: string;
  readonly file_size_bytes: number;
  readonly description: string | null;
  readonly rows_processed: number;
  readonly rows_skipped: number;
  readonly rows_failed: number;
  readonly error_details: string | null;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly created_at: string;
}
