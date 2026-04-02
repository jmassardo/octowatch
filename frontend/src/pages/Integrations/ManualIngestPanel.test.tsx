import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { ManualIngestPanel } from './ManualIngestPanel';
import type { ManualIngestJob } from '../../types/ingest';

/* ------------------------------------------------------------------ */
/*  Mocks                                                              */
/* ------------------------------------------------------------------ */

const mockUploadFile =
  vi.fn<(file: File, type: string, description?: string) => Promise<ManualIngestJob>>();
const mockGetIngestJob = vi.fn<(jobId: string) => Promise<ManualIngestJob>>();
const mockListIngestJobs = vi.fn<() => Promise<{ items: ManualIngestJob[]; total: number }>>();

vi.mock('../../api/ingest', () => ({
  uploadFile: (...args: unknown[]) => mockUploadFile(...(args as [File, string, string?])),
  getIngestJob: (...args: unknown[]) => mockGetIngestJob(...(args as [string])),
  listIngestJobs: (...args: unknown[]) => mockListIngestJobs(...(args as [])),
}));

/* ------------------------------------------------------------------ */
/*  Fixtures                                                           */
/* ------------------------------------------------------------------ */

const pendingJob: ManualIngestJob = {
  id: 'job-1',
  ingest_type: 'audit_log',
  status: 'running',
  submitted_by: 'admin',
  original_filename: 'audit-log-2025.csv',
  file_size_bytes: 14_200_000,
  description: null,
  rows_processed: 5000,
  rows_skipped: 10,
  rows_failed: 0,
  error_details: null,
  started_at: '2025-06-01T08:00:00Z',
  completed_at: null,
  created_at: '2025-06-01T08:00:00Z',
};

const completedJob: ManualIngestJob = {
  id: 'job-2',
  ingest_type: 'copilot_usage',
  status: 'completed',
  submitted_by: 'admin',
  original_filename: 'copilot-usage.json',
  file_size_bytes: 2_100_000,
  description: null,
  rows_processed: 1340,
  rows_skipped: 0,
  rows_failed: 0,
  error_details: null,
  started_at: '2025-05-28T14:00:00Z',
  completed_at: '2025-05-28T14:02:00Z',
  created_at: '2025-05-28T14:00:00Z',
};

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

beforeEach(() => {
  vi.clearAllMocks();
  mockListIngestJobs.mockResolvedValue({ items: [], total: 0 });
});

describe('ManualIngestPanel', () => {
  it('renders three upload cards', async () => {
    renderWithProviders(<ManualIngestPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('ingest-card-audit_log')).toBeInTheDocument();
    });
    expect(screen.getByTestId('ingest-card-audit_log_git')).toBeInTheDocument();
    expect(screen.getByTestId('ingest-card-copilot_usage')).toBeInTheDocument();
  });

  it('renders card titles and descriptions', async () => {
    renderWithProviders(<ManualIngestPanel />);
    await waitFor(() => {
      expect(screen.getByText('Audit Log')).toBeInTheDocument();
    });
    expect(screen.getByText('Audit Log (Git)')).toBeInTheDocument();
    expect(screen.getByText('Copilot Usage')).toBeInTheDocument();
  });

  it('renders empty import history', async () => {
    renderWithProviders(<ManualIngestPanel />);
    await waitFor(() => {
      expect(screen.getByText('No import jobs yet')).toBeInTheDocument();
    });
  });

  it('renders job history table when jobs exist', async () => {
    mockListIngestJobs.mockResolvedValue({
      items: [completedJob],
      total: 1,
    });
    renderWithProviders(<ManualIngestPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('ingest-history-table')).toBeInTheDocument();
    });
    expect(screen.getByText('copilot-usage.json')).toBeInTheDocument();
    expect(screen.getByText('1,340')).toBeInTheDocument();
  });

  it('rejects files larger than 500 MB', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ManualIngestPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('ingest-card-audit_log')).toBeInTheDocument();
    });

    const bigFile = new File(['x'], 'huge-file.csv', { type: 'text/csv' });
    Object.defineProperty(bigFile, 'size', { value: 600 * 1024 * 1024 });

    const auditCard = screen.getByTestId('ingest-card-audit_log');
    const fileInput = auditCard.querySelector('input[type="file"]')!;
    await user.upload(fileInput as HTMLInputElement, bigFile);

    await waitFor(() => {
      expect(screen.getByText(/File exceeds 500 MB limit/)).toBeInTheDocument();
    });
    expect(mockUploadFile).not.toHaveBeenCalled();
  });

  it('uploads valid file and shows job progress', async () => {
    const user = userEvent.setup();
    mockUploadFile.mockResolvedValue(pendingJob);
    mockGetIngestJob.mockResolvedValue(pendingJob);
    renderWithProviders(<ManualIngestPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('ingest-card-audit_log')).toBeInTheDocument();
    });

    const validFile = new File(['data'], 'audit-log.csv', { type: 'text/csv' });
    Object.defineProperty(validFile, 'size', { value: 14_200_000 });

    const auditCard = screen.getByTestId('ingest-card-audit_log');
    const fileInput = auditCard.querySelector('input[type="file"]')!;
    await user.upload(fileInput as HTMLInputElement, validFile);

    await waitFor(() => {
      expect(mockUploadFile).toHaveBeenCalledOnce();
    });
    await waitFor(() => {
      expect(screen.getByText('5,000 rows processed')).toBeInTheDocument();
    });
  });

  it('shows upload error when API fails', async () => {
    const user = userEvent.setup();
    mockUploadFile.mockRejectedValue(new Error('Server error'));
    renderWithProviders(<ManualIngestPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('ingest-card-audit_log')).toBeInTheDocument();
    });

    const validFile = new File(['data'], 'audit-log.csv', { type: 'text/csv' });

    const auditCard = screen.getByTestId('ingest-card-audit_log');
    const fileInput = auditCard.querySelector('input[type="file"]')!;
    await user.upload(fileInput as HTMLInputElement, validFile);

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument();
    });
  });

  it('shows skipped and failed row counts', async () => {
    const jobWithIssues: ManualIngestJob = {
      ...pendingJob,
      rows_skipped: 25,
      rows_failed: 3,
    };
    mockUploadFile.mockResolvedValue(jobWithIssues);
    mockGetIngestJob.mockResolvedValue(jobWithIssues);

    const user = userEvent.setup();
    renderWithProviders(<ManualIngestPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('ingest-card-audit_log')).toBeInTheDocument();
    });

    const validFile = new File(['data'], 'audit-log.csv', { type: 'text/csv' });
    const auditCard = screen.getByTestId('ingest-card-audit_log');
    const fileInput = auditCard.querySelector('input[type="file"]')!;
    await user.upload(fileInput as HTMLInputElement, validFile);

    await waitFor(() => {
      expect(screen.getByText('25 skipped')).toBeInTheDocument();
    });
    expect(screen.getByText('3 failed')).toBeInTheDocument();
  });

  it('has accessible upload buttons for each card', async () => {
    renderWithProviders(<ManualIngestPanel />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Upload Audit Log' })).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Upload Audit Log (Git)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Upload Copilot Usage' })).toBeInTheDocument();
  });

  it('displays intro text', async () => {
    renderWithProviders(<ManualIngestPanel />);
    await waitFor(() => {
      expect(screen.getByText(/Upload exported data files/)).toBeInTheDocument();
    });
  });
});
