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
      created_at: '2024-01-01T00:00:00Z',
      triggered_by: 'admin',
      started_at: '2025-06-01T08:00:00Z',
      completed_at: '2025-06-01T08:15:00Z',
    },
    {
      id: 'run-2',
      status: 'failed',
      trigger_type: 'scheduled',
      created_at: '2024-01-01T00:00:00Z',
      triggered_by: null,
      started_at: '2025-05-31T10:00:00Z',
      completed_at: '2025-05-31T10:05:00Z',
    },
    {
      id: 'run-3',
      status: 'cancelled',
      trigger_type: 'manual',
      created_at: '2024-01-01T00:00:00Z',
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
  created_at: '2024-01-01T00:00:00Z',
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

  it('expands row to show org breakdown on click', async () => {
    const user = userEvent.setup();
    mockListSyncRuns.mockResolvedValue(runsResponse);
    mockGetSyncRun.mockResolvedValue(runDetail);
    renderWithProviders(<SyncRunHistory />);
    await waitFor(() => {
      expect(screen.getByText('admin')).toBeInTheDocument();
    });
    // Click the first row (admin) to expand the org breakdown
    const adminRow = screen.getByText('admin').closest('tr')!;
    await user.click(adminRow);
    // Should show org names: 'acme' (from repos cursor) and 'Enterprise' (null org → users)
    await waitFor(() => {
      expect(screen.getByText('acme')).toBeInTheDocument();
    });
    expect(screen.getByText('Enterprise')).toBeInTheDocument();
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
    // First click — opens the org breakdown
    await user.click(adminRow);
    await waitFor(() => {
      expect(screen.getByText('acme')).toBeInTheDocument();
    });
    // Second click on the same row — toggles breakdown closed
    await user.click(adminRow);
    await waitFor(() => {
      expect(screen.queryByText('acme')).not.toBeInTheDocument();
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

  it('clicking an org row opens the category drawer', async () => {
    const user = userEvent.setup();
    mockListSyncRuns.mockResolvedValue(runsResponse);
    mockGetSyncRun.mockResolvedValue(runDetail);
    renderWithProviders(<SyncRunHistory />);
    await waitFor(() => expect(screen.getByText('admin')).toBeInTheDocument());

    // Expand the run row to show orgs
    await user.click(screen.getByText('admin').closest('tr')!);
    await waitFor(() => expect(screen.getByText('acme')).toBeInTheDocument());

    // Click the org row to open the categories drawer
    const orgRow = screen.getByText('acme').closest('tr')!;
    await user.click(orgRow);

    // Drawer should show 'repos' as a category for the 'acme' org
    await waitFor(() => expect(screen.getByTestId('org-categories-table')).toBeInTheDocument());
    expect(screen.getByText('repos')).toBeInTheDocument();
  });

  it('clicking a category row shows logs with a back button', async () => {
    const user = userEvent.setup();
    mockListSyncRuns.mockResolvedValue(runsResponse);
    mockGetSyncRun.mockResolvedValue(runDetail);
    mockGetSyncLogs.mockResolvedValue({
      entries: [
        {
          seq: 1,
          timestamp: '2025-06-01T08:01:00Z',
          level: 'info',
          message: 'synced 500 repos',
          entity_type: 'repos',
          org: 'acme',
        },
      ],
      last_seq: 1,
    });
    renderWithProviders(<SyncRunHistory />);
    await waitFor(() => expect(screen.getByText('admin')).toBeInTheDocument());

    // Expand the run row
    await user.click(screen.getByText('admin').closest('tr')!);
    await waitFor(() => expect(screen.getByText('acme')).toBeInTheDocument());

    // Open the org drawer
    await user.click(screen.getByText('acme').closest('tr')!);
    await waitFor(() => expect(screen.getByText('repos')).toBeInTheDocument());

    // Click the category row to drill into logs
    await user.click(screen.getByText('repos').closest('tr')!);

    // Log message should appear and back button should be visible
    await waitFor(() => expect(screen.getByText('synced 500 repos')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Back to categories' })).toBeInTheDocument();
  });

  it('back button in log view returns to category list', async () => {
    const user = userEvent.setup();
    mockListSyncRuns.mockResolvedValue(runsResponse);
    mockGetSyncRun.mockResolvedValue(runDetail);
    mockGetSyncLogs.mockResolvedValue({ entries: [], last_seq: 0 });
    renderWithProviders(<SyncRunHistory />);
    await waitFor(() => expect(screen.getByText('admin')).toBeInTheDocument());

    // Navigate into logs
    await user.click(screen.getByText('admin').closest('tr')!);
    await waitFor(() => expect(screen.getByText('acme')).toBeInTheDocument());
    await user.click(screen.getByText('acme').closest('tr')!);
    await waitFor(() => expect(screen.getByText('repos')).toBeInTheDocument());
    await user.click(screen.getByText('repos').closest('tr')!);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Back to categories' })).toBeInTheDocument(),
    );

    // Click back
    await user.click(screen.getByRole('button', { name: 'Back to categories' }));

    // Should return to the category table
    await waitFor(() => expect(screen.getByTestId('org-categories-table')).toBeInTheDocument());
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
      expect(screen.getByText('acme')).toBeInTheDocument();
    });
  });
});
