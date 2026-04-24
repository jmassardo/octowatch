import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { CiCdView } from './CiCdView';

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => vi.fn() };
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

const mockGetAlwaysFailingWorkflows = vi.fn().mockResolvedValue({
  items: [
    {
      org: 'acme',
      repo: 'acme/api',
      workflow_name: 'CI',
      consecutive_count: 5,
      last_run_at: '2026-04-16T12:00:00Z',
      last_conclusion: 'failure',
    },
  ],
  total: 1,
  threshold: 3,
  lookback_days: 30,
  cached_at: null,
});

const mockGetAlwaysTimingOutWorkflows = vi.fn().mockResolvedValue({
  items: [
    {
      org: 'acme',
      repo: 'acme/web',
      workflow_name: 'Deploy',
      consecutive_count: 4,
      last_run_at: '2026-04-16T14:00:00Z',
      last_conclusion: 'timed_out',
    },
  ],
  total: 1,
  threshold: 3,
  lookback_days: 30,
  cached_at: null,
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

vi.mock('../../api/workflowMetrics', () => ({
  getAlwaysFailingWorkflows: (...args: unknown[]) => mockGetAlwaysFailingWorkflows(...args),
  getAlwaysTimingOutWorkflows: (...args: unknown[]) => mockGetAlwaysTimingOutWorkflows(...args),
}));

vi.mock('../../api/executive', () => ({
  getMetricsThatMatter: (...args: unknown[]) => mockGetMetricsThatMatter(...args),
}));

describe('CiCdView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders workflow run metrics', async () => {
    renderWithProviders(<CiCdView />);

    // 100 + 120 = 220 total runs
    expect(await screen.findByText('220')).toBeInTheDocument();
    expect(screen.getByText('Total Runs (7d)')).toBeInTheDocument();
  });

  it('renders success rate', async () => {
    renderWithProviders(<CiCdView />);

    // (85+110) / (100+120) = 195/220 = 88.6%
    expect(await screen.findByText('88.6%')).toBeInTheDocument();
    expect(screen.getByText('Success Rate')).toBeInTheDocument();
  });

  it('renders failed runs count', async () => {
    renderWithProviders(<CiCdView />);

    // 15 + 10 = 25 failed
    expect(await screen.findByText('25')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('renders succeeded runs count', async () => {
    renderWithProviders(<CiCdView />);

    // 85 + 110 = 195
    expect(await screen.findByText('195')).toBeInTheDocument();
    expect(screen.getByText('Succeeded')).toBeInTheDocument();
  });

  it('renders the always failing workflows table', async () => {
    renderWithProviders(<CiCdView />);

    expect(await screen.findByText('Always Failing (top 10)')).toBeInTheDocument();
    expect(screen.getByText('acme/api')).toBeInTheDocument();
    expect(screen.getByText('CI')).toBeInTheDocument();
  });

  it('renders the always timing out workflows table', async () => {
    renderWithProviders(<CiCdView />);

    expect(await screen.findByText('Always Timing Out (top 10)')).toBeInTheDocument();
    expect(screen.getByText('acme/web')).toBeInTheDocument();
    expect(screen.getByText('Deploy')).toBeInTheDocument();
  });

  it('shows empty message when no always-failing workflows', async () => {
    mockGetAlwaysFailingWorkflows.mockResolvedValueOnce({
      items: [],
      total: 0,
      threshold: 3,
      lookback_days: 30,
      cached_at: null,
    });

    renderWithProviders(<CiCdView />);

    expect(await screen.findByText(/No consistently failing workflows/)).toBeInTheDocument();
  });

  it('shows empty message when no always-timing-out workflows', async () => {
    mockGetAlwaysTimingOutWorkflows.mockResolvedValueOnce({
      items: [],
      total: 0,
      threshold: 3,
      lookback_days: 30,
      cached_at: null,
    });

    renderWithProviders(<CiCdView />);

    expect(await screen.findByText(/No consistently timing-out workflows/)).toBeInTheDocument();
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

  it('shows error banner on always-failing query failure', async () => {
    mockGetAlwaysFailingWorkflows.mockRejectedValueOnce(new Error('fail'));
    renderWithProviders(<CiCdView />);

    expect(await screen.findByText('Could not load always-failing workflows')).toBeInTheDocument();
  });
});
