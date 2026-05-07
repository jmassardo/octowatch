import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { SecretsPane } from './SecretsPane';

// ── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('../../api/secretScanning', () => ({
  listSecretAlerts: vi.fn(),
  getSecretAlertSummary: vi.fn(),
  getSecretAlertTrends: vi.fn(),
  getSecretAlertAuditTrail: vi.fn(),
  getPushProtectionStats: vi.fn(),
}));

vi.mock('../../components/charts/LineAreaChart', () => ({
  LineAreaChart: ({ title }: { title?: string }) => (
    <div data-testid="line-area-chart">{title}</div>
  ),
}));

vi.mock('../../components/charts/BarChart', () => ({
  BarChart: ({ title }: { title?: string }) => <div data-testid="bar-chart">{title}</div>,
}));

import {
  listSecretAlerts,
  getSecretAlertSummary,
  getSecretAlertTrends,
  getSecretAlertAuditTrail,
  getPushProtectionStats,
} from '../../api/secretScanning';

const mockListAlerts = vi.mocked(listSecretAlerts);
const mockGetSummary = vi.mocked(getSecretAlertSummary);
const mockGetTrends = vi.mocked(getSecretAlertTrends);
const mockGetAuditTrail = vi.mocked(getSecretAlertAuditTrail);
const mockGetPushStats = vi.mocked(getPushProtectionStats);

const mockSummary = {
  open_alerts: 12,
  resolved_30d: 8,
  push_protection_bypasses: 3,
  active_secrets: 5,
  mttr_hours: 72,
  open_by_type: [
    { secret_type_label: 'GitHub PAT', count: 7 },
    { secret_type_label: 'AWS Key', count: 5 },
  ],
  resolution_breakdown: [
    { resolution: 'revoked', count: 5 },
    { resolution: 'unresolved', count: 12 },
  ],
};

const mockAlerts = {
  alerts: [
    {
      id: 1,
      org_slug: 'my-org',
      alert_number: 42,
      repo_full_name: 'my-org/repo1',
      secret_type: 'github_personal_access_token',
      secret_type_display: 'GitHub PAT',
      file_path: 'src/config.ts',
      commit_sha: 'abc123',
      state: 'open',
      resolution: null,
      push_protection_bypassed: false,
      push_protection_bypassed_by: null,
      validity: 'active',
      locations_count: 1,
      resolved_by: null,
      created_at: '2024-01-15T12:00:00Z',
      updated_at: '2024-01-15T12:00:00Z',
      resolved_at: null,
      synced_at: '2024-01-16T00:00:00Z',
    },
    {
      id: 2,
      org_slug: 'my-org',
      alert_number: 43,
      repo_full_name: 'my-org/repo2',
      secret_type: 'aws_access_key_id',
      secret_type_display: 'AWS Access Key',
      file_path: null,
      commit_sha: null,
      state: 'resolved',
      resolution: 'revoked',
      push_protection_bypassed: true,
      push_protection_bypassed_by: 'octocat',
      validity: 'inactive',
      locations_count: 0,
      resolved_by: 'admin-user',
      created_at: '2024-01-10T12:00:00Z',
      updated_at: '2024-01-12T15:00:00Z',
      resolved_at: '2024-01-12T15:00:00Z',
      synced_at: '2024-01-16T00:00:00Z',
    },
  ],
  total: 2,
};

const mockTrends = {
  period: 30,
  points: Array.from({ length: 7 }, (_, i) => ({
    date: `2024-01-${String(i + 1).padStart(2, '0')}`,
    new_alerts: 2 + (i % 3),
    resolved_alerts: 1 + (i % 2),
  })),
};

const mockPushStats = {
  total: 100,
  bypassed: 15,
  blocked: 85,
  effectiveness_pct: 85.0,
};

// ── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  mockGetSummary.mockResolvedValue(mockSummary);
  mockListAlerts.mockResolvedValue(mockAlerts);
  mockGetTrends.mockResolvedValue(mockTrends);
  mockGetPushStats.mockResolvedValue(mockPushStats);
  mockGetAuditTrail.mockResolvedValue({ alert_id: 1, events: [] });
});

// ── Tests ────────────────────────────────────────────────────────────────────

describe('SecretsPane', () => {
  it('renders summary metric cards', async () => {
    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('Open Alerts')).toBeInTheDocument();
    });

    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('Resolved (30d)')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('Push Protection Bypasses')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Active Secrets')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('MTTR')).toBeInTheDocument();
    expect(screen.getByText('3d')).toBeInTheDocument(); // 72h = 3d
  });

  it('renders alert table with rows', async () => {
    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('my-org/repo1')).toBeInTheDocument();
    });

    expect(screen.getAllByText('GitHub PAT').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('AWS Access Key')).toBeInTheDocument();
    expect(screen.getByText('my-org/repo2')).toBeInTheDocument();
  });

  it('renders state labels for alerts', async () => {
    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('open')).toBeInTheDocument();
    });

    expect(screen.getByText('resolved')).toBeInTheDocument();
  });

  it('renders validity labels', async () => {
    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('active')).toBeInTheDocument();
    });

    expect(screen.getByText('inactive')).toBeInTheDocument();
  });

  it('renders filter dropdowns', async () => {
    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('All states')).toBeInTheDocument();
    });

    expect(screen.getByText('All validity')).toBeInTheDocument();
    expect(screen.getByText('All push protection')).toBeInTheDocument();
    expect(screen.getByText('All secret types')).toBeInTheDocument();
  });

  it('filters by state when state dropdown changes', async () => {
    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('All states')).toBeInTheDocument();
    });

    const stateSelect = screen.getByDisplayValue('All states');
    fireEvent.change(stateSelect, { target: { value: 'open' } });

    await waitFor(() => {
      expect(mockListAlerts).toHaveBeenCalledWith(50, 0, 'open', undefined, undefined, undefined);
    });
  });

  it('renders charts when data is available', async () => {
    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('Alert Trend (30d)')).toBeInTheDocument();
    });

    expect(screen.getByText('Open by Secret Type')).toBeInTheDocument();
    expect(screen.getByText('Push Protection')).toBeInTheDocument();
  });

  it('opens detail drawer on row click', async () => {
    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('my-org/repo1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('my-org/repo1'));

    await waitFor(() => {
      expect(screen.getByText('Secret Scanning Alert')).toBeInTheDocument();
    });

    expect(screen.getAllByText('Repository').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Validity').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Audit Trail')).toBeInTheDocument();
  });

  it('shows error banner when summary fails', async () => {
    mockGetSummary.mockRejectedValue(new Error('API error'));

    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load secret scanning summary')).toBeInTheDocument();
    });
  });

  it('shows error banner when alerts fail', async () => {
    mockListAlerts.mockRejectedValue(new Error('API error'));

    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('Failed to load secret scanning alerts')).toBeInTheDocument();
    });
  });

  it('shows push protection bypass filter for bypassed alerts', async () => {
    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('All push protection')).toBeInTheDocument();
    });

    const bypassSelect = screen.getByDisplayValue('All push protection');
    fireEvent.change(bypassSelect, { target: { value: 'yes' } });

    await waitFor(() => {
      expect(mockListAlerts).toHaveBeenCalledWith(50, 0, undefined, undefined, undefined, true);
    });
  });

  it('renders MTTR as hours when less than 24h', async () => {
    mockGetSummary.mockResolvedValue({ ...mockSummary, mttr_hours: 12 });

    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('12h')).toBeInTheDocument();
    });
  });

  it('renders MTTR as <1h when very small', async () => {
    mockGetSummary.mockResolvedValue({ ...mockSummary, mttr_hours: 0.5 });

    renderWithProviders(<SecretsPane />);

    await waitFor(() => {
      expect(screen.getByText('<1h')).toBeInTheDocument();
    });
  });
});
