import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { SyncStatusPage } from './index';

/* ------------------------------------------------------------------ */
/*  Mocks                                                              */
/* ------------------------------------------------------------------ */

const mockGetSyncStatus = vi.fn();
const mockListSyncRuns = vi.fn();
const mockGetSyncSchedule = vi.fn();
const mockGetSyncConfig = vi.fn();

vi.mock('../../api/sync', () => ({
  getSyncStatus: (...args: unknown[]) => mockGetSyncStatus(...args),
  listSyncRuns: (...args: unknown[]) => mockListSyncRuns(...args),
  getSyncSchedule: (...args: unknown[]) => mockGetSyncSchedule(...args),
  getSyncConfig: (...args: unknown[]) => mockGetSyncConfig(...args),
  triggerSync: vi.fn().mockResolvedValue({ run_id: 'r', status: 'pending' }),
  cancelSyncRun: vi.fn().mockResolvedValue(undefined),
  updateSyncConfig: vi.fn().mockResolvedValue({}),
  updateSyncSchedule: vi.fn().mockResolvedValue({}),
  getSyncLogs: vi.fn().mockResolvedValue({ entries: [], last_seq: 0 }),
  getSyncRun: vi.fn().mockResolvedValue(null),
}));

const mockHasPermission = vi.fn();

vi.mock('../../hooks/usePermissions', () => ({
  usePermissions: () => ({
    permissions: [],
    roles: [],
    isLoading: false,
    hasPermission: (...args: unknown[]) => mockHasPermission(...args),
    hasAnyPermission: () => true,
    hasRole: () => false,
  }),
}));

/* ------------------------------------------------------------------ */
/*  Defaults                                                           */
/* ------------------------------------------------------------------ */

const defaultSyncStatus = {
  id: 'run-1',
  status: 'completed',
  trigger_type: 'manual',
  triggered_by: 'admin',
  scope: 'full',
  started_at: '2025-06-01T08:00:00Z',
  completed_at: '2025-06-01T08:15:00Z',
  error_message: null,
  entity_counts: { repos: 150, users: 45 },
  post_processing_status: 'completed',
  cursors: [],
};

const defaultRuns = {
  items: [
    {
      id: 'run-1',
      status: 'completed' as const,
      trigger_type: 'manual' as const,
      triggered_by: 'admin',
      started_at: '2025-06-01T08:00:00Z',
      completed_at: '2025-06-01T08:15:00Z',
    },
    {
      id: 'run-2',
      status: 'completed' as const,
      trigger_type: 'scheduled' as const,
      triggered_by: null,
      started_at: '2025-05-31T08:00:00Z',
      completed_at: '2025-05-31T08:10:00Z',
    },
    {
      id: 'run-3',
      status: 'failed' as const,
      trigger_type: 'scheduled' as const,
      triggered_by: null,
      started_at: '2025-05-30T08:00:00Z',
      completed_at: '2025-05-30T08:02:00Z',
    },
  ],
  total: 3,
  page: 1,
  page_size: 20,
  has_next: false,
};

const defaultSchedule = {
  enabled: true,
  interval_hours: 24,
  scope: 'full',
  next_run_at: '2025-06-02T08:00:00Z',
  last_completed_at: '2025-06-01T08:15:00Z',
};

const defaultConfig = {
  app_id: 12345,
  enterprise_slug: 'my-corp',
  installation_ids: [],
  sync_enabled: true,
  interval_days: 60,
  orgs: ['my-org'],
};

/* ------------------------------------------------------------------ */
/*  Render helper                                                      */
/* ------------------------------------------------------------------ */

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/monitoring/sync-status']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/monitoring/sync-status" element={<SyncStatusPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

describe('SyncStatusPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHasPermission.mockReturnValue(true);
    mockGetSyncStatus.mockResolvedValue(defaultSyncStatus);
    mockListSyncRuns.mockResolvedValue(defaultRuns);
    mockGetSyncSchedule.mockResolvedValue(defaultSchedule);
    mockGetSyncConfig.mockResolvedValue(defaultConfig);
  });

  /* ---------------------------------------------------------------- */
  /*  Page structure                                                    */
  /* ---------------------------------------------------------------- */

  it('renders page title and description', async () => {
    renderPage();

    expect(screen.getByRole('heading', { level: 1, name: /sync status/i })).toBeInTheDocument();
    expect(screen.getByText(/monitor data synchronization health/i)).toBeInTheDocument();
  });

  it('renders breadcrumbs', async () => {
    renderPage();

    expect(screen.getByText('Monitoring')).toBeInTheDocument();
    // "Sync Status" appears in both breadcrumb and heading
    const syncStatusElements = screen.getAllByText('Sync Status');
    expect(syncStatusElements.length).toBeGreaterThanOrEqual(2);
  });

  /* ---------------------------------------------------------------- */
  /*  Health banner                                                     */
  /* ---------------------------------------------------------------- */

  it('shows healthy banner when all runs are successful', async () => {
    mockListSyncRuns.mockResolvedValue({
      ...defaultRuns,
      items: defaultRuns.items.filter((r) => r.status === 'completed'),
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('health-banner')).toBeInTheDocument();
    });

    expect(screen.getByText('All Syncs Healthy')).toBeInTheDocument();
  });

  it('shows degraded banner when some runs failed', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('health-banner')).toBeInTheDocument();
    });

    // 1 of 3 failed → degraded
    expect(screen.getByText('Sync Degraded')).toBeInTheDocument();
  });

  it('shows unhealthy banner when many runs failed', async () => {
    mockListSyncRuns.mockResolvedValue({
      ...defaultRuns,
      items: [
        { ...defaultRuns.items[0], status: 'failed' },
        { ...defaultRuns.items[1], status: 'failed' },
        { ...defaultRuns.items[2], status: 'failed' },
      ],
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Sync Unhealthy')).toBeInTheDocument();
    });
  });

  it('shows unknown banner when no runs exist', async () => {
    mockListSyncRuns.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      has_next: false,
    });
    mockGetSyncStatus.mockResolvedValue(null);
    mockGetSyncConfig.mockResolvedValue({ ...defaultConfig, orgs: [] });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('No Sync Data')).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Sync type cards                                                   */
  /* ---------------------------------------------------------------- */

  it('renders sync type cards', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Full Sync')).toBeInTheDocument();
    });

    // Should also render org-specific card
    expect(screen.getByText('Org: my-org')).toBeInTheDocument();
  });

  it('renders sparkline visualization', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Full Sync')).toBeInTheDocument();
    });

    const sparklines = screen.getAllByRole('img', { name: /recent sync run results/i });
    expect(sparklines.length).toBeGreaterThan(0);
  });

  /* ---------------------------------------------------------------- */
  /*  Schedule card                                                     */
  /* ---------------------------------------------------------------- */

  it('renders schedule information', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Sync Schedule')).toBeInTheDocument();
    });

    expect(screen.getByText('Every 24 hours')).toBeInTheDocument();
    expect(screen.getByText('full')).toBeInTheDocument();
  });

  it('shows schedule enabled status', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Sync Schedule')).toBeInTheDocument();
    });

    expect(screen.getByText('Enabled')).toBeInTheDocument();
  });

  it('shows schedule disabled status', async () => {
    mockGetSyncSchedule.mockResolvedValue({
      ...defaultSchedule,
      enabled: false,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Sync Schedule')).toBeInTheDocument();
    });

    expect(screen.getByText('Disabled')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Recent runs table                                                 */
  /* ---------------------------------------------------------------- */

  it('renders recent runs table', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('recent-runs-table')).toBeInTheDocument();
    });

    expect(screen.getByText('admin')).toBeInTheDocument();

    // Check the runs table has status labels (use getAllByText since
    // statuses also appear in the sync cards)
    const completedLabels = screen.getAllByText('completed');
    expect(completedLabels.length).toBeGreaterThanOrEqual(1);
    const failedLabels = screen.getAllByText('failed');
    expect(failedLabels.length).toBeGreaterThanOrEqual(1);
  });

  it('shows empty state when no runs exist', async () => {
    mockListSyncRuns.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      has_next: false,
    });
    mockGetSyncStatus.mockResolvedValue(null);
    mockGetSyncConfig.mockResolvedValue({ ...defaultConfig, orgs: [] });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('No sync runs recorded yet')).toBeInTheDocument();
    });
  });

  /* ---------------------------------------------------------------- */
  /*  Permission handling                                               */
  /* ---------------------------------------------------------------- */

  it('shows permission error when user lacks admin_settings view', async () => {
    mockHasPermission.mockReturnValue(false);

    renderPage();

    expect(screen.getByText(/you do not have permission to view sync status/i)).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Loading state                                                     */
  /* ---------------------------------------------------------------- */

  it('shows loading state while data is fetching', () => {
    mockGetSyncStatus.mockReturnValue(new Promise(() => {}));
    mockListSyncRuns.mockReturnValue(new Promise(() => {}));

    renderPage();

    expect(screen.getByText(/loading sync status/i)).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Error state                                                       */
  /* ---------------------------------------------------------------- */

  it('shows error banner when API fails', async () => {
    mockGetSyncStatus.mockRejectedValue(new Error('Network error'));
    mockListSyncRuns.mockRejectedValue(new Error('Network error'));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/failed to load sync status/i)).toBeInTheDocument();
    });
  });
});
