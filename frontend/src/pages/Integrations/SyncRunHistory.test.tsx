import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { SyncRunHistory } from './SyncRunHistory';
import type { SyncRunsResponse, SyncRun } from '../../types/sync';

/* ------------------------------------------------------------------ */
/*  Mocks                                                              */
/* ------------------------------------------------------------------ */

const mockListSyncRuns = vi.fn<() => Promise<SyncRunsResponse>>();
const mockGetSyncRun = vi.fn<(runId: string) => Promise<SyncRun>>();
const mockGetSyncLogs = vi.fn();

vi.mock('../../api/sync', () => ({
  listSyncRuns: (...args: unknown[]) => mockListSyncRuns(...(args as [])),
  getSyncRun: (...args: unknown[]) => mockGetSyncRun(...(args as [string])),
  getSyncLogs: (...args: unknown[]) => mockGetSyncLogs(...args),
}));

/* ------------------------------------------------------------------ */
/*  Fixtures                                                           */
/* ------------------------------------------------------------------ */

const runsResponse: SyncRunsResponse = {
  items: [
    {
      id: 'run-1',
      status: 'completed',
      trigger_type: 'manual',
      triggered_by: 'admin',
      started_at: '2025-06-01T08:00:00Z',
      completed_at: '2025-06-01T08:15:00Z',
    },
    {
      id: 'run-2',
      status: 'failed',
      trigger_type: 'scheduled',
      triggered_by: null,
      started_at: '2025-05-31T10:00:00Z',
      completed_at: '2025-05-31T10:05:00Z',
    },
    {
      id: 'run-3',
      status: 'cancelled',
      trigger_type: 'manual',
      triggered_by: 'dev-user',
      started_at: '2025-05-30T12:00:00Z',
      completed_at: '2025-05-30T12:02:00Z',
    },
  ],
  total: 3,
  page: 1,
  page_size: 10,
  has_next: false,
};

const runDetail: SyncRun = {
  id: 'run-1',
  status: 'completed',
  trigger_type: 'manual',
  triggered_by: 'admin',
  scope: 'full',
  started_at: '2025-06-01T08:00:00Z',
  completed_at: '2025-06-01T08:15:00Z',
  error_message: null,
  entity_counts: { repos: 500 },
  post_processing_status: null,
  cursors: [
    {
      entity_type: 'repos',
      org: 'acme',
      status: 'completed',
      items_synced: 500,
      last_cursor: null,
    },
    { entity_type: 'users', org: null, status: 'completed', items_synced: 100, last_cursor: null },
  ],
};

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

beforeEach(() => {
  vi.clearAllMocks();
  mockGetSyncLogs.mockResolvedValue({ entries: [], last_seq: 0 });
});

describe('SyncRunHistory', () => {
  it('renders loading state', () => {
    mockListSyncRuns.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<SyncRunHistory />);
    expect(screen.getByText('Loading history…')).toBeInTheDocument();
  });

  it('renders error state with retry button', async () => {
    mockListSyncRuns.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<SyncRunHistory />);
    await waitFor(() => {
      expect(screen.getByText('Failed to load sync history')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('renders empty state', async () => {
    mockListSyncRuns.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
      has_next: false,
    });
    renderWithProviders(<SyncRunHistory />);
    await waitFor(() => {
      expect(screen.getByText('No sync runs yet')).toBeInTheDocument();
    });
  });

  it('renders history table with correct runs', async () => {
    mockListSyncRuns.mockResolvedValue(runsResponse);
    renderWithProviders(<SyncRunHistory />);
    await waitFor(() => {
      expect(screen.getByTestId('sync-history-table')).toBeInTheDocument();
    });
    expect(screen.getByText('admin')).toBeInTheDocument();
    expect(screen.getByText('scheduled')).toBeInTheDocument();
    expect(screen.getByText('dev-user')).toBeInTheDocument();
    expect(screen.getByText('completed')).toBeInTheDocument();
    expect(screen.getByText('failed')).toBeInTheDocument();
    expect(screen.getByText('cancelled')).toBeInTheDocument();
  });

  it('expands row to show entity details on click', async () => {
    const user = userEvent.setup();
    mockListSyncRuns.mockResolvedValue(runsResponse);
    mockGetSyncRun.mockResolvedValue(runDetail);
    renderWithProviders(<SyncRunHistory />);
    await waitFor(() => {
      expect(screen.getByText('admin')).toBeInTheDocument();
    });
    // Click the first row (admin)
    const adminRow = screen.getByText('admin').closest('tr')!;
    await user.click(adminRow);
    // Wait for detail to load
    await waitFor(() => {
      expect(screen.getByText('repos')).toBeInTheDocument();
    });
    expect(screen.getByText('500')).toBeInTheDocument();
    expect(screen.getByText('users')).toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument();
  });

  it('collapses expanded row on second click', async () => {
    const user = userEvent.setup();
    mockListSyncRuns.mockResolvedValue(runsResponse);
    mockGetSyncRun.mockResolvedValue(runDetail);
    renderWithProviders(<SyncRunHistory />);
    await waitFor(() => {
      expect(screen.getByText('admin')).toBeInTheDocument();
    });
    const adminRow = screen.getByText('admin').closest('tr')!;
    // First click — opens the drawer
    await user.click(adminRow);
    await waitFor(() => {
      expect(screen.getByText('repos')).toBeInTheDocument();
    });
    // Second click on the same row — toggles drawer closed
    await user.click(adminRow);
    await waitFor(() => {
      expect(screen.queryByText('repos')).not.toBeInTheDocument();
    });
  });

  it('shows error message in expanded detail for failed run', async () => {
    const user = userEvent.setup();
    mockListSyncRuns.mockResolvedValue(runsResponse);
    const failedDetail: SyncRun = {
      ...runDetail,
      id: 'run-2',
      status: 'failed',
      error_message: 'Token expired',
      cursors: [],
    };
    mockGetSyncRun.mockResolvedValue(failedDetail);
    renderWithProviders(<SyncRunHistory />);
    await waitFor(() => {
      expect(screen.getByText('scheduled')).toBeInTheDocument();
    });
    const scheduledRow = screen.getByText('scheduled').closest('tr')!;
    await user.click(scheduledRow);
    await waitFor(() => {
      expect(screen.getByText('Token expired')).toBeInTheDocument();
    });
  });

  it('rows are keyboard accessible', async () => {
    const user = userEvent.setup();
    mockListSyncRuns.mockResolvedValue(runsResponse);
    mockGetSyncRun.mockResolvedValue(runDetail);
    renderWithProviders(<SyncRunHistory />);
    await waitFor(() => {
      expect(screen.getByText('admin')).toBeInTheDocument();
    });
    const adminRow = screen.getByText('admin').closest('tr')!;
    adminRow.focus();
    await user.keyboard('{Enter}');
    await waitFor(() => {
      expect(screen.getByText('repos')).toBeInTheDocument();
    });
  });
});
