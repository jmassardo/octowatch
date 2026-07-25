import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router';
import { SyncStatusPage } from './index';

/* ------------------------------------------------------------------ */
/*  Mocks                                                              */
/* ------------------------------------------------------------------ */

const mockGetSyncStatus = vi.fn();
const mockListSyncRuns = vi.fn();
const mockGetSyncSchedule = vi.fn();
const mockGetSyncConfig = vi.fn();
const mockGetSyncRun = vi.fn();

vi.mock('../../api/sync', () => ({
  getSyncStatus: (...args: unknown[]) => mockGetSyncStatus(...args),
  listSyncRuns: (...args: unknown[]) => mockListSyncRuns(...args),
  getSyncSchedule: (...args: unknown[]) => mockGetSyncSchedule(...args),
  getSyncConfig: (...args: unknown[]) => mockGetSyncConfig(...args),
  getSyncRun: (...args: unknown[]) => mockGetSyncRun(...args),
  triggerSync: vi.fn().mockResolvedValue({ run_id: 'r', status: 'pending' }),
  cancelSyncRun: vi.fn().mockResolvedValue(undefined),
  updateSyncConfig: vi.fn().mockResolvedValue({}),
  updateSyncSchedule: vi.fn().mockResolvedValue({}),
  getSyncLogs: vi.fn().mockResolvedValue({ entries: [], last_seq: 0 }),
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
    scopedOrgs: [],
    scopedRepos: [],
    scopeType: 'global',
    isOrgInScope: () => true,
    isRepoInScope: () => true,
    canEdit: () => false,
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
  page_size: 5,
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

const defaultRunDetail = {
  id: 'run-1',
  status: 'completed' as const,
  trigger_type: 'manual' as const,
  triggered_by: 'admin',
  scope: 'full',
  started_at: '2025-06-01T08:00:00Z',
  completed_at: '2025-06-01T08:15:00Z',
  error_message: null,
  entity_counts: { repos: 150, users: 45 },
  post_processing_status: 'completed',
  cursors: [
    {
      entity_type: 'repositories',
      org: 'my-org',
      status: 'completed' as const,
      items_synced: 150,
      last_cursor: 'abc123',
    },
  ],
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
      <MemoryRouter initialEntries={['/monitoring/sync-status']}>
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
    mockGetSyncRun.mockResolvedValue(defaultRunDetail);
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

  it('shows unhealthy banner with error details when current run has failed', async () => {
    const failedRun = {
      ...defaultSyncStatus,
      status: 'failed',
      error_message: 'Rate limit exceeded for GitHub API',
      cursors: [
        {
          entity_type: 'repositories',
          org: 'my-org',
          status: 'failed',
          items_synced: 50,
          last_cursor: 'cursor-xyz',
        },
      ],
    };
    mockGetSyncStatus.mockResolvedValue(failedRun);
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
      expect(screen.getByTestId('health-banner-error-details')).toBeInTheDocument();
    });

    expect(screen.getByText('Rate limit exceeded for GitHub API')).toBeInTheDocument();
    expect(screen.getByText('repositories')).toBeInTheDocument();
    expect(screen.getByText('cursor-xyz')).toBeInTheDocument();
    expect(screen.getByText(/wait for the rate limit window/i)).toBeInTheDocument();
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
      page_size: 5,
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
  /*  Overall status + schedule layout                                  */
  /* ---------------------------------------------------------------- */

  it('renders overall status card and schedule card', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Overall Status')).toBeInTheDocument();
    });

    expect(screen.getByText('Sync Schedule')).toBeInTheDocument();
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
  /*  Recent runs table with pagination                                 */
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

  it('paginates runs table at 5 per page', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('recent-runs-table')).toBeInTheDocument();
    });

    // listSyncRuns should have been called with page 1, page_size 5
    expect(mockListSyncRuns).toHaveBeenCalledWith(1, 5);
  });

  it('changes page when pagination is used', async () => {
    mockListSyncRuns.mockResolvedValue({
      ...defaultRuns,
      total: 12,
      has_next: true,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('recent-runs-table')).toBeInTheDocument();
    });

    // Click next page
    const nextBtn = screen.getByRole('button', { name: /next/i });
    fireEvent.click(nextBtn);

    await waitFor(() => {
      expect(mockListSyncRuns).toHaveBeenCalledWith(2, 5);
    });
  });

  it('shows empty state when no runs exist', async () => {
    mockListSyncRuns.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 5,
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
  /*  Run detail drawer                                                 */
  /* ---------------------------------------------------------------- */

  it('opens drawer with run details when row is clicked', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('recent-runs-table')).toBeInTheDocument();
    });

    // Click the first row
    const rows = screen.getByTestId('recent-runs-table').querySelectorAll('tbody tr');
    fireEvent.click(rows[0]!);

    await waitFor(() => {
      expect(screen.getByTestId('drawer-panel')).toBeInTheDocument();
    });

    expect(screen.getByText('Sync Run Details')).toBeInTheDocument();
  });

  it('shows entity counts and cursor progress in drawer', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('recent-runs-table')).toBeInTheDocument();
    });

    const rows = screen.getByTestId('recent-runs-table').querySelectorAll('tbody tr');
    fireEvent.click(rows[0]!);

    await waitFor(() => {
      expect(screen.getByTestId('run-detail-drawer-content')).toBeInTheDocument();
    });

    // Check entity counts are shown
    expect(screen.getByText('Entities Synced')).toBeInTheDocument();
    const drawerContent = screen.getByTestId('run-detail-drawer-content');
    expect(drawerContent).toHaveTextContent('150');
    expect(drawerContent).toHaveTextContent('45');

    // Check cursor progress
    expect(screen.getByText('Cursor Progress')).toBeInTheDocument();
    expect(screen.getByText('repositories')).toBeInTheDocument();
  });

  it('closes drawer when close button is clicked', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('recent-runs-table')).toBeInTheDocument();
    });

    const rows = screen.getByTestId('recent-runs-table').querySelectorAll('tbody tr');
    fireEvent.click(rows[0]!);

    await waitFor(() => {
      expect(screen.getByTestId('drawer-panel')).toBeInTheDocument();
    });

    const closeBtn = screen.getByRole('button', { name: /close/i });
    fireEvent.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByTestId('drawer-panel')).not.toBeInTheDocument();
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
