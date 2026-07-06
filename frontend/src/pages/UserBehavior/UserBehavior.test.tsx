import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { UserBehaviorPage } from './index';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockRiskSummary = {
  total_users_with_signals: 12,
  high_risk_count: 2,
  medium_risk_count: 4,
  low_risk_count: 6,
  anomaly_count: 3,
  top_categories: [
    {
      category: 'security_bypass',
      label: 'Security Bypasses',
      description: 'Disabling protections, removing branch rules, bypassing 2FA',
      event_count: 15,
    },
    {
      category: 'permission_change',
      label: 'Permission Changes',
      description: 'Role escalations, team membership changes, access grants',
      event_count: 10,
    },
  ],
  lookback_days: 30,
};

const mockRiskyUsers = {
  users: [
    {
      user_login: 'risky-admin',
      risk_score: 22,
      risk_level: 'high' as const,
      signals: [
        {
          action: 'protected_branch.destroy',
          label: 'Branch protection removed',
          category: 'security_bypass',
          count: 3,
          weight: 15,
          last_seen: '2025-01-15T10:00:00Z',
        },
        {
          action: 'personal_access_token.create',
          label: 'PAT created',
          category: 'credential_activity',
          count: 2,
          weight: 6,
          last_seen: '2025-01-14T08:00:00Z',
        },
      ],
      category_breakdown: [
        { category: 'security_bypass', label: 'Security Bypasses', count: 3 },
        { category: 'credential_activity', label: 'Credential Activity', count: 2 },
      ],
      orgs: ['acme-corp'],
      last_risky_action_at: '2025-01-15T10:00:00Z',
    },
    {
      user_login: 'moderate-user',
      risk_score: 8,
      risk_level: 'medium' as const,
      signals: [
        {
          action: 'org.update_member',
          label: 'Org role change',
          category: 'permission_change',
          count: 2,
          weight: 6,
          last_seen: '2025-01-12T14:00:00Z',
        },
      ],
      category_breakdown: [
        { category: 'permission_change', label: 'Permission Changes', count: 2 },
      ],
      orgs: ['acme-corp'],
      last_risky_action_at: '2025-01-12T14:00:00Z',
    },
  ],
  total: 2,
  page: 1,
  page_size: 50,
};

const mockAnomalies = {
  anomalies: [
    {
      user_login: 'spike-user',
      recent_event_count: 500,
      baseline_daily_avg: 10,
      activity_ratio: 3.5,
      recent_action_types: 20,
      baseline_action_types: 8,
      recent_ips: 5,
      baseline_ips: 2,
      deviation_reasons: ['Activity volume 3.5x above baseline', 'Performing unusual action types'],
    },
  ],
  lookback_days: 30,
};

const mockPermissionDrift = {
  users: [
    {
      user_login: 'over-privileged',
      total_events: 15,
      admin_events: 12,
      dev_events: 2,
      admin_pct: 80.0,
      last_active: '2025-01-10T09:00:00Z',
      status: 'review_recommended' as const,
      reason: 'High admin activity with minimal development — may have excessive permissions',
    },
  ],
  lookback_days: 90,
};

vi.mock('../../api/userBehavior', () => ({
  getRiskSummary: vi.fn(() => Promise.resolve(mockRiskSummary)),
  getRiskyUsers: vi.fn(() => Promise.resolve(mockRiskyUsers)),
  getAnomalies: vi.fn(() => Promise.resolve(mockAnomalies)),
  getPermissionDrift: vi.fn(() => Promise.resolve(mockPermissionDrift)),
}));

vi.mock('../../hooks/useHelp', () => ({
  useHelp: () => ({ isOpen: false, toggle: vi.fn(), helpKey: null }),
  HelpProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

function renderPage(route = '/user-behavior/risky-users') {
  return renderWithProviders(<UserBehaviorPage />, {
    route,
    routePath: '/user-behavior/:tab',
  });
}

describe('UserBehaviorPage', () => {
  it('renders page title and security-focused description', async () => {
    renderPage();
    expect(await screen.findByText('User Behavior')).toBeInTheDocument();
    expect(screen.getByText(/Security-focused behavioral analysis/)).toBeInTheDocument();
  });

  it('shows context banner explaining the page purpose', async () => {
    renderPage();
    expect(await screen.findByText(/What this page shows:/)).toBeInTheDocument();
    expect(screen.getByText(/different from Developer Activity/)).toBeInTheDocument();
  });

  it('displays risk summary metrics after loading', async () => {
    renderPage();
    expect(await screen.findByTestId('users-with-signals')).toHaveTextContent('12');
    expect(screen.getByTestId('high-risk-count')).toHaveTextContent('2');
    expect(screen.getByTestId('medium-risk-count')).toHaveTextContent('4');
    expect(screen.getByTestId('low-risk-count')).toHaveTextContent('6');
    expect(screen.getByTestId('anomaly-count')).toHaveTextContent('3');
  });

  it('shows risk categories breakdown', async () => {
    renderPage();
    expect(await screen.findByText('Top Risk Categories')).toBeInTheDocument();
    expect(screen.getByText('Security Bypasses')).toBeInTheDocument();
    expect(screen.getByText('Permission Changes')).toBeInTheDocument();
    expect(screen.getByText('15 events')).toBeInTheDocument();
  });

  it('shows helpful context for metric thresholds', async () => {
    renderPage();
    expect(await screen.findByText(/Score ≥ 15 — investigate promptly/)).toBeInTheDocument();
    expect(screen.getByText(/Score 7–14 — worth monitoring/)).toBeInTheDocument();
  });

  it('renders risky users table with data', async () => {
    renderPage();
    expect(await screen.findByText('risky-admin')).toBeInTheDocument();
    expect(screen.getByText('moderate-user')).toBeInTheDocument();
  });

  it('shows risk level labels in user table', async () => {
    renderPage();
    expect(await screen.findByText('high')).toBeInTheDocument();
    expect(screen.getByText('medium')).toBeInTheDocument();
  });

  it('shows signal tags in risky users table', async () => {
    renderPage();
    expect(await screen.findByText(/Branch protection removed/)).toBeInTheDocument();
    expect(screen.getByText(/PAT created/)).toBeInTheDocument();
  });

  it('has time range filter', async () => {
    renderPage();
    const select = await screen.findByLabelText(/Time range/i);
    expect(select).toBeInTheDocument();
    expect(select).toHaveValue('30');
  });

  it('has risk level filter on risky users tab', async () => {
    renderPage();
    const select = await screen.findByLabelText(/Risk level/i);
    expect(select).toBeInTheDocument();
    expect(select).toHaveValue('');
  });

  it('switches to anomaly detection tab', async () => {
    const user = userEvent.setup();
    renderPage();

    const anomalyTab = await screen.findByRole('tab', { name: /Anomaly Detection/i });
    await user.click(anomalyTab);

    await waitFor(() => {
      expect(screen.getByText('spike-user')).toBeInTheDocument();
    });
    expect(screen.getByText('3.5x')).toBeInTheDocument();
    expect(screen.getByText(/Activity volume 3.5x above baseline/)).toBeInTheDocument();
  });

  it('switches to permission drift tab', async () => {
    const user = userEvent.setup();
    renderPage();

    const permTab = await screen.findByRole('tab', { name: /Permission Drift/i });
    await user.click(permTab);

    await waitFor(() => {
      expect(screen.getByText('over-privileged')).toBeInTheDocument();
    });
    expect(screen.getByText('Review')).toBeInTheDocument();
    expect(screen.getByText(/may have excessive permissions/)).toBeInTheDocument();
  });

  it('renders tab descriptions explaining what each tab shows', async () => {
    renderPage();
    expect(
      await screen.findByText(/Users ranked by risk score based on security-sensitive actions/),
    ).toBeInTheDocument();
  });

  it('time range filter updates the lookback period', async () => {
    const user = userEvent.setup();
    renderPage();

    const select = await screen.findByLabelText(/Time range/i);
    await user.selectOptions(select, '7');
    expect(select).toHaveValue('7');
  });

  it('shows three navigation tabs', async () => {
    renderPage();
    expect(await screen.findByRole('tab', { name: /Risky Users/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Anomaly Detection/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Permission Drift/i })).toBeInTheDocument();
  });

  // ─── Clickable Chips ────────────────────────────────────────────────────────

  it('clicking high risk chip filters to high risk and shows filter banner', async () => {
    const user = userEvent.setup();
    renderPage();

    // Wait for metrics to load
    await screen.findByTestId('high-risk-count');

    // Click the high risk chip
    const highChip = screen.getByRole('button', { pressed: false, name: /High Risk/i });
    await user.click(highChip);

    // Should show filter banner
    expect(screen.getByTestId('active-chip-filter')).toBeInTheDocument();
    expect(screen.getByText(/high risk/i, { selector: 'strong' })).toBeInTheDocument();

    // Risk level filter should be set to high
    const select = screen.getByLabelText(/Risk level/i);
    expect(select).toHaveValue('high');
  });

  it('clicking a risk chip again deselects it and clears filter', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByTestId('high-risk-count');

    const highChip = screen.getByRole('button', { name: /High Risk/i });
    await user.click(highChip);
    expect(screen.getByTestId('active-chip-filter')).toBeInTheDocument();

    // Click again to deselect
    await user.click(highChip);
    expect(screen.queryByTestId('active-chip-filter')).not.toBeInTheDocument();
  });

  it('clear filter button removes chip filter', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByTestId('high-risk-count');

    const medChip = screen.getByRole('button', { name: /Medium Risk/i });
    await user.click(medChip);

    const clearBtn = screen.getByRole('button', { name: /Clear filter/i });
    await user.click(clearBtn);

    expect(screen.queryByTestId('active-chip-filter')).not.toBeInTheDocument();
  });

  it('clicking a category card shows filter banner with category name', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Security Bypasses');

    const categoryBtn = screen.getByRole('button', { name: /Security Bypasses/i });
    await user.click(categoryBtn);

    expect(screen.getByTestId('active-chip-filter')).toBeInTheDocument();
    expect(screen.getByText(/security bypass/i, { selector: 'strong' })).toBeInTheDocument();
  });

  // ─── Column Filters ─────────────────────────────────────────────────────────

  it('risky users table has filterable Level and Orgs columns', async () => {
    renderPage();

    await screen.findByText('risky-admin');

    // DataTable renders filter row when filterable columns exist
    const filterRow = screen.getByTestId('filter-row');
    expect(filterRow).toBeInTheDocument();

    // Should have filter inputs for User, Level, and Orgs
    expect(screen.getByLabelText('Filter Level')).toBeInTheDocument();
    expect(screen.getByLabelText('Filter Orgs')).toBeInTheDocument();
  });

  it('anomaly table has filterable Activity Multiplier column', async () => {
    const user = userEvent.setup();
    renderPage();

    const anomalyTab = await screen.findByRole('tab', { name: /Anomaly Detection/i });
    await user.click(anomalyTab);

    await waitFor(() => {
      expect(screen.getByText('spike-user')).toBeInTheDocument();
    });

    expect(screen.getByLabelText('Filter Activity Multiplier')).toBeInTheDocument();
    expect(screen.getByLabelText('Filter Recent IPs')).toBeInTheDocument();
  });

  it('permission drift table has filterable Status and Admin % columns', async () => {
    const user = userEvent.setup();
    renderPage();

    const permTab = await screen.findByRole('tab', { name: /Permission Drift/i });
    await user.click(permTab);

    await waitFor(() => {
      expect(screen.getByText('over-privileged')).toBeInTheDocument();
    });

    expect(screen.getByLabelText('Filter Status')).toBeInTheDocument();
    expect(screen.getByLabelText('Filter Admin %')).toBeInTheDocument();
  });

  // ─── Row Click → Drawer ─────────────────────────────────────────────────────

  it('clicking a risky user row opens the detail drawer', async () => {
    const user = userEvent.setup();
    renderPage();

    const row = await screen.findByText('risky-admin');
    await user.click(row);

    // Drawer should be open with user details
    const drawer = await screen.findByTestId('drawer-panel');
    expect(drawer).toBeInTheDocument();
    expect(within(drawer).getByText('@risky-admin')).toBeInTheDocument();
    expect(within(drawer).getByText('View on GitHub ↗')).toBeInTheDocument();
    expect(within(drawer).getByText('Risk Assessment')).toBeInTheDocument();
    expect(within(drawer).getByText('Signal Timeline')).toBeInTheDocument();
    expect(within(drawer).getByText('Org Memberships')).toBeInTheDocument();
    expect(within(drawer).getByText('Recommended Actions')).toBeInTheDocument();
  });

  it('clicking an anomaly row opens the detail drawer with activity comparison', async () => {
    const user = userEvent.setup();
    renderPage();

    const anomalyTab = await screen.findByRole('tab', { name: /Anomaly Detection/i });
    await user.click(anomalyTab);

    const row = await screen.findByText('spike-user');
    await user.click(row);

    const drawer = await screen.findByTestId('drawer-panel');
    expect(within(drawer).getByText('@spike-user')).toBeInTheDocument();
    expect(within(drawer).getByText('Activity Comparison')).toBeInTheDocument();
    expect(within(drawer).getByText('Deviation Signals')).toBeInTheDocument();
    expect(within(drawer).getByText('IP Address History')).toBeInTheDocument();
  });

  it('clicking a permission drift row opens the detail drawer with status', async () => {
    const user = userEvent.setup();
    renderPage();

    const permTab = await screen.findByRole('tab', { name: /Permission Drift/i });
    await user.click(permTab);

    const row = await screen.findByText('over-privileged');
    await user.click(row);

    const drawer = await screen.findByTestId('drawer-panel');
    expect(within(drawer).getByText('@over-privileged')).toBeInTheDocument();
    expect(within(drawer).getByText('Status Assessment')).toBeInTheDocument();
    expect(within(drawer).getByText('Activity Breakdown')).toBeInTheDocument();
  });

  it('drawer can be closed by clicking the close button', async () => {
    const user = userEvent.setup();
    renderPage();

    const row = await screen.findByText('risky-admin');
    await user.click(row);

    const drawer = await screen.findByTestId('drawer-panel');
    expect(drawer).toBeInTheDocument();

    const closeBtn = within(drawer).getByRole('button', { name: /Close/i });
    await user.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByTestId('drawer-panel')).not.toBeInTheDocument();
    });
  });

  it('drawer shows GitHub link with correct URL', async () => {
    const user = userEvent.setup();
    renderPage();

    const row = await screen.findByText('risky-admin');
    await user.click(row);

    const drawer = await screen.findByTestId('drawer-panel');
    const ghLink = within(drawer).getByText('View on GitHub ↗');
    expect(ghLink).toHaveAttribute('href', 'https://github.com/risky-admin');
    expect(ghLink).toHaveAttribute('target', '_blank');
  });
});
