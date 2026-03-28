import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { SyncPanel } from './SyncPanel';
import type { SyncRun, SyncConfig } from '../../types/sync';

/* ------------------------------------------------------------------ */
/*  Mocks                                                              */
/* ------------------------------------------------------------------ */

const mockGetSyncStatus = vi.fn<() => Promise<SyncRun>>();
const mockTriggerSync = vi.fn<() => Promise<{ run_id: string; status: string }>>();
const mockCancelSyncRun = vi.fn<(runId: string) => Promise<void>>();
const mockGetSyncConfig = vi.fn<() => Promise<SyncConfig>>();

vi.mock('../../api/sync', () => ({
  getSyncStatus: (...args: unknown[]) => mockGetSyncStatus(...(args as [])),
  triggerSync: (...args: unknown[]) => mockTriggerSync(...(args as [])),
  cancelSyncRun: (...args: unknown[]) => mockCancelSyncRun(...(args as [string])),
  getSyncConfig: (...args: unknown[]) => mockGetSyncConfig(...(args as [])),
}));

/* ------------------------------------------------------------------ */
/*  Fixtures                                                           */
/* ------------------------------------------------------------------ */

const completedRun: SyncRun = {
  id: 'run-1',
  status: 'completed',
  trigger_type: 'manual',
  triggered_by: 'admin',
  scope: 'full',
  started_at: '2025-06-01T08:00:00Z',
  completed_at: '2025-06-01T08:15:00Z',
  error_message: null,
  entity_counts: { repos: 500, users: 100 },
  cursors: [
    { entity_type: 'repos', org: 'acme', status: 'completed', items_synced: 500, last_cursor: null },
    { entity_type: 'users', org: null, status: 'completed', items_synced: 100, last_cursor: null },
  ],
};

const runningRun: SyncRun = {
  id: 'run-2',
  status: 'running',
  trigger_type: 'manual',
  triggered_by: 'admin',
  scope: 'full',
  started_at: new Date(Date.now() - 120_000).toISOString(),
  completed_at: null,
  error_message: null,
  entity_counts: null,
  cursors: [
    { entity_type: 'repos', org: 'acme', status: 'completed', items_synced: 300, last_cursor: 'abc' },
    { entity_type: 'users', org: null, status: 'in_progress', items_synced: 50, last_cursor: 'def' },
    { entity_type: 'teams', org: 'acme', status: 'pending', items_synced: 0, last_cursor: null },
  ],
};

const failedRun: SyncRun = {
  id: 'run-3',
  status: 'failed',
  trigger_type: 'scheduled',
  triggered_by: null,
  scope: 'full',
  started_at: '2025-06-01T10:00:00Z',
  completed_at: '2025-06-01T10:05:00Z',
  error_message: 'Authentication token expired',
  entity_counts: { repos: 200 },
  cursors: [
    { entity_type: 'repos', org: 'acme', status: 'failed', items_synced: 200, last_cursor: null },
  ],
};

const syncConfig: SyncConfig = {
  app_id: 12345,
  enterprise_slug: 'acme-corp',
  installation_ids: [{ org: 'acme', installation_id: 1 }],
  sync_enabled: true,
  interval_days: 1,
  orgs: ['acme'],
};

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

beforeEach(() => {
  vi.clearAllMocks();
  mockGetSyncConfig.mockResolvedValue(syncConfig);
});

describe('SyncPanel', () => {
  it('renders loading state', () => {
    mockGetSyncStatus.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<SyncPanel />);
    expect(screen.getByText('Loading sync status…')).toBeInTheDocument();
  });

  it('renders error state with retry button', async () => {
    mockGetSyncStatus.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByText('Failed to load sync status')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });

  it('renders completed sync summary', async () => {
    mockGetSyncStatus.mockResolvedValue(completedRun);
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByText('completed')).toBeInTheDocument();
    });
    expect(screen.getByText('600')).toBeInTheDocument(); // 500 + 100
    expect(screen.getByText('15m 0s')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run Sync Now' })).toBeEnabled();
  });

  it('renders running state with progress and cancel button', async () => {
    mockGetSyncStatus.mockResolvedValue(runningRun);
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByText('Syncing')).toBeInTheDocument();
    });
    expect(screen.getByTestId('sync-progress')).toBeInTheDocument();
    expect(screen.getByText('1/3 entities · 33%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run Sync Now' })).toBeDisabled();
  });

  it('renders entity table with correct data', async () => {
    mockGetSyncStatus.mockResolvedValue(runningRun);
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('entity-table')).toBeInTheDocument();
    });
    expect(screen.getByText('repos')).toBeInTheDocument();
    // "acme" appears for both repos and teams org
    const acmeCells = screen.getAllByText('acme');
    expect(acmeCells).toHaveLength(2);
    expect(screen.getByText('in progress')).toBeInTheDocument();
    expect(screen.getByText('300')).toBeInTheDocument();
  });

  it('triggers sync when Run Sync Now is clicked', async () => {
    const user = userEvent.setup();
    mockGetSyncStatus.mockResolvedValue(completedRun);
    mockTriggerSync.mockResolvedValue({ run_id: 'new-run', status: 'pending' });
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Run Sync Now' })).toBeEnabled();
    });
    await user.click(screen.getByRole('button', { name: 'Run Sync Now' }));
    expect(mockTriggerSync).toHaveBeenCalledOnce();
  });

  it('cancels sync when Cancel is clicked', async () => {
    const user = userEvent.setup();
    mockGetSyncStatus.mockResolvedValue(runningRun);
    mockCancelSyncRun.mockResolvedValue(undefined);
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mockCancelSyncRun).toHaveBeenCalledWith('run-2');
  });

  it('shows error message for failed sync', async () => {
    mockGetSyncStatus.mockResolvedValue(failedRun);
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByText('failed')).toBeInTheDocument();
    });
    expect(screen.getByText('Authentication token expired')).toBeInTheDocument();
  });

  it('shows trigger error when sync trigger fails', async () => {
    const user = userEvent.setup();
    mockGetSyncStatus.mockResolvedValue(completedRun);
    mockTriggerSync.mockRejectedValue(new Error('Rate limited'));
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Run Sync Now' })).toBeEnabled();
    });
    await user.click(screen.getByRole('button', { name: 'Run Sync Now' }));
    await waitFor(() => {
      expect(screen.getByText('Rate limited')).toBeInTheDocument();
    });
  });

  it('shows pending status as Queued', async () => {
    const pendingRun: SyncRun = {
      ...runningRun,
      status: 'pending',
      started_at: new Date().toISOString(),
    };
    mockGetSyncStatus.mockResolvedValue(pendingRun);
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByText('Queued')).toBeInTheDocument();
    });
  });
});
