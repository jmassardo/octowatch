import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { CiCdView } from './CiCdView';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const MOCK_BUCKETS = [
  {
    bucket: '2026-04-10',
    workflow_runs_total: 100,
    workflow_runs_succeeded: 85,
    workflow_runs_failed: 15,
    success_rate_pct: 85.0,
    unique_workflows: 5,
  },
  {
    bucket: '2026-04-11',
    workflow_runs_total: 120,
    workflow_runs_succeeded: 110,
    workflow_runs_failed: 10,
    success_rate_pct: 91.7,
    unique_workflows: 6,
  },
];

const mockGetActionsVolumeReport = vi.fn().mockResolvedValue({
  report_type: 'actions-volume',
  org: null,
  granularity: 'daily',
  window_days: 7,
  data_source: 'events',
  generated_at: '2026-04-17T00:00:00Z',
  data: MOCK_BUCKETS,
});

const mockGetWorkflowHealth = vi.fn().mockResolvedValue({
  workflows: [
    {
      repo: 'acme/api',
      workflow_name: 'CI',
      total_runs: 50,
      successes: 30,
      failures: 20,
      failure_rate_pct: 40.0,
      last_run: '2026-04-16T12:00:00Z',
    },
    {
      repo: 'acme/web',
      workflow_name: 'Deploy',
      total_runs: 80,
      successes: 75,
      failures: 5,
      failure_rate_pct: 6.3,
      last_run: '2026-04-16T14:00:00Z',
    },
  ],
});

const mockGetMetricsThatMatter = vi.fn().mockResolvedValue({
  period_days: 30,
  generated_at: '2026-04-17T00:00:00Z',
  shipping_faster: {
    avg_pr_lifecycle_hours: 18.5,
    avg_pr_review_rounds: 1.2,
    deployment_frequency_per_week: 4.3,
    pr_merge_rate_pct: 92.1,
    trend: [],
  },
  shipping_safer: {
    workflow_success_rate_pct: 88.5,
    codeql_alerts_opened: 5,
    codeql_alerts_closed: 3,
    secret_alerts_opened: 1,
    secret_alerts_resolved: 0,
    branch_protection_compliance_pct: 95.0,
    change_failure_rate_pct: 12.3,
    trend: [],
  },
  shipping_cheaper: {
    failed_run_waste_pct: 8.5,
    rerun_rate_pct: 3.2,
    automation_merge_rate_pct: 45.0,
    avg_pr_review_rounds: 1.2,
    top_wasteful_workflows: [],
    trend: [],
  },
});

vi.mock('../../api/reports', () => ({
  getActionsVolumeReport: (...args: unknown[]) => mockGetActionsVolumeReport(...args),
}));

vi.mock('../../api/healthSignals', () => ({
  getWorkflowHealth: (...args: unknown[]) => mockGetWorkflowHealth(...args),
}));

vi.mock('../../api/executive', () => ({
  getMetricsThatMatter: (...args: unknown[]) => mockGetMetricsThatMatter(...args),
}));

describe('CiCdView', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it('renders workflow run metrics', async () => {
    renderWithProviders(<CiCdView />);

    // 100 + 120 = 220 total runs
    expect(await screen.findByText('220')).toBeInTheDocument();
    expect(screen.getByText('Workflow runs (7d)')).toBeInTheDocument();
  });

  it('renders success rate', async () => {
    renderWithProviders(<CiCdView />);

    // (85+110) / (100+120) = 195/220 = 88.6%
    expect(await screen.findByText('88.6%')).toBeInTheDocument();
    expect(screen.getByText('Success rate')).toBeInTheDocument();
  });

  it('renders failed runs count', async () => {
    renderWithProviders(<CiCdView />);

    // 15 + 10 = 25 failed
    expect(await screen.findByText('25')).toBeInTheDocument();
    expect(screen.getByText('Failed runs')).toBeInTheDocument();
  });

  it('renders unhealthy workflows count', async () => {
    renderWithProviders(<CiCdView />);

    // Only acme/api has failure_rate_pct > 20
    await screen.findByText('Unhealthy workflows');
    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('renders the top failing workflows table', async () => {
    renderWithProviders(<CiCdView />);

    expect(await screen.findByText('Top Failing Workflows')).toBeInTheDocument();
    expect(screen.getByText('acme/api')).toBeInTheDocument();
    expect(screen.getByText('CI')).toBeInTheDocument();
    expect(screen.getByText('acme/web')).toBeInTheDocument();
    expect(screen.getByText('Deploy')).toBeInTheDocument();
  });

  it('shows workflows sorted by failure rate descending', async () => {
    renderWithProviders(<CiCdView />);

    await screen.findByText('acme/api');

    // acme/api (40%) should appear before acme/web (6.3%)
    const rows = screen.getAllByRole('row');
    // rows[0] = header row, rows[1] = filter row (DataTable renders filter inputs),
    // rows[2] = first data row, rows[3] = second data row
    const firstDataRow = rows[2];
    const secondDataRow = rows[3];
    expect(firstDataRow.textContent).toContain('acme/api');
    expect(secondDataRow.textContent).toContain('acme/web');
  });

  it('navigates to /workflows on workflow row click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CiCdView />);

    await screen.findByText('acme/api');

    const row = screen.getByText('acme/api').closest('tr');
    expect(row).toBeTruthy();
    await user.click(row!);

    expect(mockNavigate).toHaveBeenCalledWith('/workflows');
  });

  it('renders DORA quick glance section', async () => {
    renderWithProviders(<CiCdView />);

    expect(await screen.findByText('DORA Quick Glance')).toBeInTheDocument();
    expect(screen.getByText('Deployment Frequency')).toBeInTheDocument();
    expect(screen.getByText('Change Failure Rate')).toBeInTheDocument();
    expect(screen.getByText('Lead Time')).toBeInTheDocument();
  });

  it('renders DORA metric values from Metrics That Matter', async () => {
    renderWithProviders(<CiCdView />);

    expect(await screen.findByText('4.3/wk')).toBeInTheDocument(); // deployment freq
    expect(screen.getByText('12.3%')).toBeInTheDocument(); // change failure rate
    expect(screen.getByText('19h')).toBeInTheDocument(); // lead time (18.5 rounded)
  });

  it('shows error banner on actions report failure', async () => {
    mockGetActionsVolumeReport.mockRejectedValueOnce(new Error('fail'));
    renderWithProviders(<CiCdView />);

    expect(await screen.findByText('Could not load actions volume report')).toBeInTheDocument();
  });

  it('shows empty table when no workflows', async () => {
    mockGetWorkflowHealth.mockResolvedValueOnce({ workflows: [] });
    renderWithProviders(<CiCdView />);

    expect(await screen.findByText('No workflow data available')).toBeInTheDocument();
  });
});
