import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { SyncPanel } from './SyncPanel';
import type { SyncRun, SyncConfig, SyncSchedule } from '../../types/sync';

/* ------------------------------------------------------------------ */
/*  Mocks                                                              */
/* ------------------------------------------------------------------ */

const mockGetSyncStatus = vi.fn<() => Promise<SyncRun>>();
const mockTriggerSync = vi.fn<() => Promise<{ run_id: string; status: string }>>();
const mockCancelSyncRun = vi.fn<(runId: string) => Promise<void>>();
const mockGetSyncConfig = vi.fn<() => Promise<SyncConfig>>();
const mockGetSyncSchedule = vi.fn<() => Promise<SyncSchedule>>();
const mockUpdateSyncSchedule = vi.fn<() => Promise<SyncSchedule>>();

vi.mock('../../api/sync', () => ({
  getSyncStatus: (...args: unknown[]) => mockGetSyncStatus(...(args as [])),
  triggerSync: (...args: unknown[]) => mockTriggerSync(...(args as [])),
  cancelSyncRun: (...args: unknown[]) => mockCancelSyncRun(...(args as [string])),
  getSyncConfig: (...args: unknown[]) => mockGetSyncConfig(...(args as [])),
  getSyncSchedule: (...args: unknown[]) => mockGetSyncSchedule(...(args as [])),
  updateSyncSchedule: (...args: unknown[]) => mockUpdateSyncSchedule(...(args as [])),
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

const defaultSchedule: SyncSchedule = {
  enabled: false,
  interval_hours: 24,
  scope: 'full',
  next_run_at: null,
  last_completed_at: null,
};

const enabledSchedule: SyncSchedule = {
  enabled: true,
  interval_hours: 12,
  scope: 'repositories',
  next_run_at: '2025-07-01T20:00:00Z',
  last_completed_at: '2025-07-01T08:00:00Z',
};

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

beforeEach(() => {
  vi.clearAllMocks();
  mockGetSyncConfig.mockResolvedValue(syncConfig);
  mockGetSyncSchedule.mockResolvedValue(defaultSchedule);
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

/* ------------------------------------------------------------------ */
/*  Schedule section tests                                             */
/* ------------------------------------------------------------------ */

describe('ScheduleSection', () => {
  it('renders the schedule section with default values', async () => {
    mockGetSyncStatus.mockResolvedValue(completedRun);
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('schedule-section')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Enable automatic sync schedule')).not.toBeChecked();
    expect(screen.getByText('Not scheduled')).toBeInTheDocument();
    expect(screen.getByText('Never')).toBeInTheDocument();
  });

  it('renders schedule with enabled schedule data', async () => {
    mockGetSyncStatus.mockResolvedValue(completedRun);
    mockGetSyncSchedule.mockResolvedValue(enabledSchedule);
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('schedule-section')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Enable automatic sync schedule')).toBeChecked();
    // Check the dropdowns have the right values
    const intervalSelect = screen.getByLabelText('Schedule interval') as HTMLSelectElement;
    expect(intervalSelect.value).toBe('12');
    const scopeSelect = screen.getByLabelText('Sync scope') as HTMLSelectElement;
    expect(scopeSelect.value).toBe('repositories');
  });

  it('save button is disabled when no changes made', async () => {
    mockGetSyncStatus.mockResolvedValue(completedRun);
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('schedule-section')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Save Schedule' })).toBeDisabled();
  });

  it('save button enables after toggling enabled checkbox', async () => {
    const user = userEvent.setup();
    mockGetSyncStatus.mockResolvedValue(completedRun);
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('schedule-section')).toBeInTheDocument();
    });
    await user.click(screen.getByLabelText('Enable automatic sync schedule'));
    expect(screen.getByRole('button', { name: 'Save Schedule' })).toBeEnabled();
  });

  it('calls updateSyncSchedule on save', async () => {
    const user = userEvent.setup();
    mockGetSyncStatus.mockResolvedValue(completedRun);
    mockUpdateSyncSchedule.mockResolvedValue({
      ...defaultSchedule,
      enabled: true,
    });
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('schedule-section')).toBeInTheDocument();
    });
    await user.click(screen.getByLabelText('Enable automatic sync schedule'));
    await user.click(screen.getByRole('button', { name: 'Save Schedule' }));
    expect(mockUpdateSyncSchedule).toHaveBeenCalledOnce();
  });

  it('shows success message after saving', async () => {
    const user = userEvent.setup();
    mockGetSyncStatus.mockResolvedValue(completedRun);
    mockUpdateSyncSchedule.mockResolvedValue({
      ...defaultSchedule,
      enabled: true,
    });
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('schedule-section')).toBeInTheDocument();
    });
    await user.click(screen.getByLabelText('Enable automatic sync schedule'));
    await user.click(screen.getByRole('button', { name: 'Save Schedule' }));
    await waitFor(() => {
      expect(screen.getByText('Schedule saved successfully.')).toBeInTheDocument();
    });
  });

  it('shows error message when save fails', async () => {
    const user = userEvent.setup();
    mockGetSyncStatus.mockResolvedValue(completedRun);
    mockUpdateSyncSchedule.mockRejectedValue(new Error('Server error'));
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('schedule-section')).toBeInTheDocument();
    });
    await user.click(screen.getByLabelText('Enable automatic sync schedule'));
    await user.click(screen.getByRole('button', { name: 'Save Schedule' }));
    await waitFor(() => {
      expect(screen.getByText('Failed to save schedule. Please try again.')).toBeInTheDocument();
    });
  });

  it('renders schedule loading state', async () => {
    mockGetSyncStatus.mockResolvedValue(completedRun);
    mockGetSyncSchedule.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByText('Loading schedule…')).toBeInTheDocument();
    });
  });

  it('renders schedule error state', async () => {
    mockGetSyncStatus.mockResolvedValue(completedRun);
    mockGetSyncSchedule.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByText('Failed to load schedule')).toBeInTheDocument();
    });
  });

  it('changing interval enables save button', async () => {
    const user = userEvent.setup();
    mockGetSyncStatus.mockResolvedValue(completedRun);
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('schedule-section')).toBeInTheDocument();
    });
    await user.selectOptions(screen.getByLabelText('Schedule interval'), '48');
    expect(screen.getByRole('button', { name: 'Save Schedule' })).toBeEnabled();
  });

  it('changing scope enables save button', async () => {
    const user = userEvent.setup();
    mockGetSyncStatus.mockResolvedValue(completedRun);
    renderWithProviders(<SyncPanel />);
    await waitFor(() => {
      expect(screen.getByTestId('schedule-section')).toBeInTheDocument();
    });
    await user.selectOptions(screen.getByLabelText('Sync scope'), 'teams');
    expect(screen.getByRole('button', { name: 'Save Schedule' })).toBeEnabled();
  });
});
