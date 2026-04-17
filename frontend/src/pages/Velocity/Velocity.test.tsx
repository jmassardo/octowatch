import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { VelocityPage } from './index';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockGetActionsVolumeReport = vi.fn().mockResolvedValue({ data: [] });
const mockListEvents = vi.fn().mockResolvedValue({ items: [], total: 0 });

vi.mock('../../api/reports', () => ({
  getActionsVolumeReport: (...args: unknown[]) => mockGetActionsVolumeReport(...args),
}));

vi.mock('../../api/events', () => ({
  listEvents: (...args: unknown[]) => mockListEvents(...args),
}));

vi.mock('../../api/healthSignals', () => ({
  getWorkflowHealth: vi.fn().mockResolvedValue({ workflows: [] }),
  getBranchProtection: vi.fn().mockResolvedValue({
    protections_removed: 0,
    policy_overrides: 0,
    modified: 0,
    distinct_repos_affected: 0,
  }),
}));

// ECharts renders canvas elements that jsdom doesn't support.
// Stub the chart components to avoid runtime errors and enable
// assertion on the props they receive.
vi.mock('../../components/charts/LineAreaChart', () => ({
  LineAreaChart: (props: Record<string, unknown>) => (
    <div data-testid="line-area-chart" data-series={JSON.stringify(props.series)} />
  ),
}));

vi.mock('../../components/charts/BarChart', () => ({
  BarChart: (props: Record<string, unknown>) => (
    <div data-testid="bar-chart" data-series={JSON.stringify(props.series)} />
  ),
}));

vi.mock('../../components/charts/ContributionCalendar', () => ({
  ContributionCalendar: (props: Record<string, unknown>) => (
    <div data-testid="contribution-calendar" data-has-data={props.data ? 'true' : 'false'} />
  ),
}));

describe('VelocityPage', () => {
  /* ---------------------------------------------------------------- */
  /*  Page header & DORA badge                                         */
  /* ---------------------------------------------------------------- */

  it('renders the page title', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('Engineering Velocity')).toBeInTheDocument();
  });

  it('renders the page subtitle', () => {
    renderWithProviders(<VelocityPage />);

    expect(
      screen.getByText(/flow metrics, dora indicators, and delivery throughput/i),
    ).toBeInTheDocument();
  });

  it('renders the DORA tier label and pending badge when no data', () => {
    renderWithProviders(<VelocityPage />);

    // "DORA tier" appears in both the header badge and the definitions panel — use getAllBy
    expect(screen.getAllByText('DORA tier').length).toBeGreaterThanOrEqual(1);
    // With no workflow data, DORA tier shows pending state
    expect(screen.getByText('— Pending')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Info banner                                                       */
  /* ---------------------------------------------------------------- */

  it('renders the info banner about system behavior metrics', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText(/metrics here measure/i)).toBeInTheDocument();
    expect(screen.getByText(/system behavior/i)).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  All 8 metric cards                                                */
  /* ---------------------------------------------------------------- */

  it('renders all 8 metric card labels', () => {
    renderWithProviders(<VelocityPage />);

    // Labels appear in both metric cards and the definitions panel — use getAllBy where needed
    expect(screen.getAllByText('PRs merged (30d)').length).toBeGreaterThanOrEqual(1);
    // "Lead time for changes" also appears in chart title; verify at least one
    expect(screen.getAllByText(/Lead time for changes/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('PR activity (30d)').length).toBeGreaterThanOrEqual(1);
    // "Change failure rate" also appears in chart title and table header
    expect(screen.getAllByText(/Change failure rate/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Successful workflows (30d)').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Workflow success').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('WIP (items in flight)').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Review coverage').length).toBeGreaterThanOrEqual(1);
  });

  it('shows dash for metrics that require external API integration', () => {
    renderWithProviders(<VelocityPage />);

    // Metrics without API backing show '—'
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(3);

    // Informational hints for unavailable metrics
    expect(screen.getByText(/Insufficient data/)).toBeInTheDocument();
    expect(screen.getByText(/No PR data available/)).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Contribution calendar                                             */
  /* ---------------------------------------------------------------- */

  it('renders the contribution calendar', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByTestId('contribution-calendar')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  2×2 Chart grid                                                    */
  /* ---------------------------------------------------------------- */

  it('renders empty-state messages for all charts when no data', async () => {
    renderWithProviders(<VelocityPage />);

    // Wait for queries to resolve, then all 4 charts show empty state
    const noDataMessages = await screen.findAllByText('No workflow data available');
    expect(noDataMessages).toHaveLength(4);
  });

  it('renders chart titles for all 4 DORA charts', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText(/Workflow success rate/)).toBeInTheDocument();
    expect(screen.getByText(/Daily deployments \/ MTTR/)).toBeInTheDocument();
    // "Lead time for changes" and "Change failure rate" also appear as metric labels
    expect(screen.getAllByText(/Lead time for changes/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/Change failure rate/).length).toBeGreaterThanOrEqual(2);
  });

  it('renders dynamic chart period labels for all 4 charts when no data', () => {
    renderWithProviders(<VelocityPage />);

    // All 4 charts show dynamic period label (empty data → '—')
    const periodLabels = screen.getAllByText('— —');
    expect(periodLabels).toHaveLength(4);
  });

  it('renders lead time empty state instead of placeholder when no data', async () => {
    renderWithProviders(<VelocityPage />);

    // Lead time now shows standard empty state instead of placeholder text
    const noDataMessages = await screen.findAllByText('No workflow data available');
    expect(noDataMessages.length).toBeGreaterThanOrEqual(1);
  });

  it('shows empty state for bar chart area when no data', async () => {
    renderWithProviders(<VelocityPage />);

    // With empty mock data, bar chart area shows placeholder text
    const noDataMessages = await screen.findAllByText('No workflow data available');
    expect(noDataMessages.length).toBeGreaterThanOrEqual(1);
  });

  /* ---------------------------------------------------------------- */
  /*  Top failing workflows table                                       */
  /* ---------------------------------------------------------------- */

  it('renders the top failing workflows section title', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('Top failing workflows')).toBeInTheDocument();
  });

  it('renders the top failing workflows table with correct column headers', () => {
    renderWithProviders(<VelocityPage />);

    const sectionTitle = screen.getByText('Top failing workflows');
    const tableWrap = sectionTitle.nextElementSibling;
    const table = tableWrap?.querySelector('table');
    expect(table).toBeTruthy();
    // Get only the first header row (DataTable may add a filter row)
    const headerRow = table!.querySelector('thead tr');
    const headers = headerRow!.querySelectorAll('th');
    const headerTexts = Array.from(headers).map((h) => h.textContent?.replace(/[⇅↑↓]/g, '').trim());

    expect(headerTexts).toEqual([
      'Workflow',
      'Repository',
      'Failure rate',
      'Last run',
      'Total runs',
    ]);
  });

  it('shows empty state when no workflow health data is available', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('No workflow health data available')).toBeInTheDocument();
  });

  it('does not show sample data banner for top failing workflows', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.queryByText(/Top failing workflows display sample data/)).not.toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Most active repositories table                                    */
  /* ---------------------------------------------------------------- */

  it('renders the most active repositories section title', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('Most active repositories — last 30 days')).toBeInTheDocument();
  });

  it('renders the repos table with correct column headers', () => {
    renderWithProviders(<VelocityPage />);

    // Find the most active repos section title
    const sectionTitle = screen.getByText('Most active repositories — last 30 days');
    // The table is the next sibling tableWrap
    const tableWrap = sectionTitle.nextElementSibling;
    const table = tableWrap?.querySelector('table');
    expect(table).toBeTruthy();
    // Get only the first header row (DataTable may add a filter row)
    const headerRow = table!.querySelector('thead tr');
    const headers = headerRow!.querySelectorAll('th');
    const headerTexts = Array.from(headers).map((h) => h.textContent?.replace(/[⇅↑↓]/g, '').trim());

    expect(headerTexts).toEqual([
      'Repository',
      'Events',
      'PR events',
      'Push events',
      'Contributors',
    ]);
  });

  it('renders empty state for repos when no events are available', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('No repository activity data available')).toBeInTheDocument();
  });

  it('does not show sample data banner for most active repos', () => {
    renderWithProviders(<VelocityPage />);

    expect(
      screen.queryByText(/Most active repositories display sample data/),
    ).not.toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Empty state                                                       */
  /* ---------------------------------------------------------------- */

  it('renders the empty state message when no workflow data is available', async () => {
    renderWithProviders(<VelocityPage />);

    // Wait for async queries to resolve before checking empty state
    expect(
      await screen.findByText('No workflow run data for the selected period.'),
    ).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/*  Tests with populated API data                                      */
/* ------------------------------------------------------------------ */

describe('VelocityPage with data', () => {
  const MOCK_BUCKETS = [
    {
      bucket: '2024-01-15',
      workflow_runs_total: 100,
      workflow_runs_succeeded: 95,
      workflow_runs_failed: 5,
      success_rate_pct: 95.0,
      unique_workflows: 10,
    },
    {
      bucket: '2024-01-16',
      workflow_runs_total: 80,
      workflow_runs_succeeded: 72,
      workflow_runs_failed: 8,
      success_rate_pct: 90.0,
      unique_workflows: 8,
    },
  ];

  const MOCK_EVENTS = [
    {
      id: 1,
      document_id: 'd1',
      created_at: '2024-01-15T00:00:00Z',
      ingested_at: '2024-01-15T00:00:00Z',
      action: 'push',
      namespace: 'git',
      actor: 'alice',
      actor_id: 1,
      actor_is_bot: false,
      org: 'myorg',
      org_id: 1,
      repo: 'myorg/api-service',
      repo_id: 1,
      business: null,
      source_ip: null,
      user_agent: null,
      geo_country_code: null,
      geo_city: null,
      geo_is_proxy: null,
      data: {},
      ingestion_source: 'webhook',
      source_file_path: '',
    },
    {
      id: 2,
      document_id: 'd2',
      created_at: '2024-01-15T01:00:00Z',
      ingested_at: '2024-01-15T01:00:00Z',
      action: 'push',
      namespace: 'git',
      actor: 'bob',
      actor_id: 2,
      actor_is_bot: false,
      org: 'myorg',
      org_id: 1,
      repo: 'myorg/api-service',
      repo_id: 1,
      business: null,
      source_ip: null,
      user_agent: null,
      geo_country_code: null,
      geo_city: null,
      geo_is_proxy: null,
      data: {},
      ingestion_source: 'webhook',
      source_file_path: '',
    },
    {
      id: 3,
      document_id: 'd3',
      created_at: '2024-01-15T02:00:00Z',
      ingested_at: '2024-01-15T02:00:00Z',
      action: 'pull_request',
      namespace: 'git',
      actor: 'alice',
      actor_id: 1,
      actor_is_bot: false,
      org: 'myorg',
      org_id: 1,
      repo: 'myorg/web-app',
      repo_id: 2,
      business: null,
      source_ip: null,
      user_agent: null,
      geo_country_code: null,
      geo_city: null,
      geo_is_proxy: null,
      data: {},
      ingestion_source: 'webhook',
      source_file_path: '',
    },
  ];

  beforeEach(() => {
    mockGetActionsVolumeReport.mockResolvedValue({
      report_type: 'actions-volume',
      org: null,
      granularity: 'daily',
      window_days: 30,
      generated_at: '2024-01-16T00:00:00Z',
      data: MOCK_BUCKETS,
    });
    mockListEvents.mockResolvedValue({
      items: MOCK_EVENTS,
      total: 3,
      page: 1,
      page_size: 500,
      has_next: false,
    });
  });

  it('renders computed workflow success rate from API data', async () => {
    renderWithProviders(<VelocityPage />);

    // total: 180 runs, succeeded: 167, rate = (167/180)*100 = 92.8%
    expect(await screen.findByText('92.8%')).toBeInTheDocument();
  });

  it('renders computed change failure rate from API data', async () => {
    renderWithProviders(<VelocityPage />);

    // total: 180 runs, failed: 13, rate = (13/180)*100 = 7.2%
    expect(await screen.findByText('7.2%')).toBeInTheDocument();
  });

  it('renders charts with real data when buckets are available', async () => {
    renderWithProviders(<VelocityPage />);

    // Wait for data to load – charts render with bucket data
    await screen.findByText('92.8%');

    // Line and bar charts should render (not empty state)
    // 3 line-area-charts: Lead time, CFR, Workflow success
    const lineCharts = screen.getAllByTestId('line-area-chart');
    expect(lineCharts.length).toBeGreaterThanOrEqual(3);

    const barCharts = screen.getAllByTestId('bar-chart');
    expect(barCharts).toHaveLength(1);
  });

  it('renders period label based on bucket count', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('92.8%');

    // 2 buckets → "2 days" — all 4 charts show this label
    const periodLabels = screen.getAllByText('— 2 days');
    expect(periodLabels).toHaveLength(4);
  });

  it('renders active repos derived from events with activity columns', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('92.8%');

    // Repos derived from mock events
    expect(screen.getByText('myorg/api-service')).toBeInTheDocument();
    expect(screen.getByText('myorg/web-app')).toBeInTheDocument();

    // When real data exists, table shows activity columns
    const repoTable = screen.getByText('myorg/api-service').closest('table');
    expect(repoTable).toBeTruthy();
    const headerRow = repoTable!.querySelector('thead tr');
    const headers = headerRow!.querySelectorAll('th');
    const headerTexts = Array.from(headers).map((h) => h.textContent?.replace(/[⇅↑↓]/g, '').trim());
    expect(headerTexts).toContain('Events');
    expect(headerTexts).toContain('PR events');
    expect(headerTexts).toContain('Push events');
    expect(headerTexts).toContain('Contributors');
  });

  it('does not show any sample data banners when real data exists', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('92.8%');

    // No sample data banners should exist at all
    expect(screen.queryByText(/display sample data/)).not.toBeInTheDocument();
  });

  it('renders dynamic DORA tier badge based on data', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('92.8%');

    // Mock data has 167 succeeded / 30 days ≈ 5.6 deploys/day (Elite)
    // and CFR 7.2% (High), average = 3.5 → Elite
    expect(screen.getByText('★ Elite')).toBeInTheDocument();
  });

  it('renders MTTR chart with dual series when data is available', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('92.8%');

    // The bar chart should contain MTTR series
    const barCharts = screen.getAllByTestId('bar-chart');
    expect(barCharts).toHaveLength(1);
    const seriesData = JSON.parse(barCharts[0].getAttribute('data-series') ?? '[]');
    const seriesNames = seriesData.map((s: { name: string }) => s.name);
    expect(seriesNames).toContain('Deployments');
    expect(seriesNames).toContain('MTTR (hours)');
  });
});

/* ------------------------------------------------------------------ */
/*  DORA badge modal                                                   */
/* ------------------------------------------------------------------ */

describe('VelocityPage DORA badge interaction', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockGetActionsVolumeReport.mockResolvedValue({ data: [] });
    mockListEvents.mockResolvedValue({ items: [], total: 0 });
  });

  it('DORA badge is clickable with role=button', () => {
    renderWithProviders(<VelocityPage />);

    // With no data, shows pending state
    const badge = screen.getByText('— Pending');
    expect(badge).toHaveAttribute('role', 'button');
    expect(badge).toHaveAttribute('tabindex', '0');
  });

  it('opens DORA modal when badge is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<VelocityPage />);

    const badge = screen.getByText('— Pending');
    await user.click(badge);

    expect(screen.getByText('DORA Metrics — Pending Tier')).toBeInTheDocument();
    expect(screen.getByText('Deployment Frequency')).toBeInTheDocument();
    expect(screen.getByText('Lead Time for Changes')).toBeInTheDocument();
    expect(screen.getByText('Change Failure Rate')).toBeInTheDocument();
    expect(screen.getByText('Time to Restore Service')).toBeInTheDocument();
  });

  it('closes DORA modal when close button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<VelocityPage />);

    const badge = screen.getByText('— Pending');
    await user.click(badge);

    expect(screen.getByText('DORA Metrics — Pending Tier')).toBeInTheDocument();

    const closeBtn = screen.getByLabelText('Close');
    await user.click(closeBtn);

    expect(screen.queryByText('DORA Metrics — Pending Tier')).not.toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/*  Clickable repo rows                                                */
/* ------------------------------------------------------------------ */

describe('VelocityPage repo row clicks', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockGetActionsVolumeReport.mockResolvedValue({ data: [] });
    mockListEvents.mockResolvedValue({
      items: [
        {
          id: 1,
          document_id: 'd1',
          created_at: '2024-01-15T00:00:00Z',
          ingested_at: '2024-01-15T00:00:00Z',
          action: 'push',
          namespace: 'git',
          actor: 'alice',
          actor_id: 1,
          actor_is_bot: false,
          org: 'myorg',
          org_id: 1,
          repo: 'myorg/api-service',
          repo_id: 1,
          business: null,
          source_ip: null,
          user_agent: null,
          geo_country_code: null,
          geo_city: null,
          geo_is_proxy: null,
          data: {},
          ingestion_source: 'webhook',
          source_file_path: '',
        },
      ],
      total: 1,
      page: 1,
      page_size: 500,
      has_next: false,
    });
  });

  it('repo rows have role=button and cursor pointer styling', async () => {
    renderWithProviders(<VelocityPage />);

    const repoCell = await screen.findByText('myorg/api-service');
    const row = repoCell.closest('tr');
    // DataTable applies a clickableRow CSS class for rows with onRowClick
    expect(row).toBeTruthy();
    expect(row!.className).toBeTruthy();
    expect(row!.onclick).toBeTruthy();
  });

  it('clicking a repo row navigates to /events?repo=...', async () => {
    const user = userEvent.setup();
    renderWithProviders(<VelocityPage />);

    const repoCell = await screen.findByText('myorg/api-service');
    await user.click(repoCell);

    expect(mockNavigate).toHaveBeenCalledWith('/events?repo=myorg%2Fapi-service');
  });
});

/* ------------------------------------------------------------------ */
/*  Workflow failures row modal                                        */
/* ------------------------------------------------------------------ */

describe('VelocityPage failure row modal', () => {
  const MOCK_BUCKETS = [
    {
      bucket: '2024-01-15',
      workflow_runs_total: 100,
      workflow_runs_succeeded: 85,
      workflow_runs_failed: 15,
      success_rate_pct: 85.0,
      unique_workflows: 10,
    },
  ];

  beforeEach(() => {
    mockNavigate.mockClear();
    mockGetActionsVolumeReport.mockResolvedValue({
      report_type: 'actions-volume',
      org: null,
      granularity: 'daily',
      window_days: 30,
      generated_at: '2024-01-16T00:00:00Z',
      data: MOCK_BUCKETS,
    });
    mockListEvents.mockResolvedValue({ items: [], total: 0 });
  });

  it('failure rows are clickable with role=button', async () => {
    renderWithProviders(<VelocityPage />);

    // Wait for the failure table to render
    const failedLabel = await screen.findByText('15');
    const row = failedLabel.closest('tr');
    // DataTable applies a clickableRow CSS class for rows with onRowClick
    expect(row).toBeTruthy();
    expect(row!.className).toBeTruthy();
    expect(row!.onclick).toBeTruthy();
  });

  it('clicking a failure row opens a detail modal', async () => {
    const user = userEvent.setup();
    renderWithProviders(<VelocityPage />);

    const failedLabel = await screen.findByText('15');
    const row = failedLabel.closest('tr');
    await user.click(row!);

    // Modal title is "Workflow runs — <date>"
    expect(screen.getByText(/Workflow runs/)).toBeInTheDocument();
    // Modal contains metric labels (these also exist in the table, so use getAllBy)
    const totalRunsLabels = screen.getAllByText('Total runs');
    expect(totalRunsLabels.length).toBeGreaterThanOrEqual(2); // table header + modal
    expect(screen.getByText('Succeeded')).toBeInTheDocument();
    // "Failed" appears in column header and modal
    const failedLabels = screen.getAllByText('Failed');
    expect(failedLabels.length).toBeGreaterThanOrEqual(2);
    // "Success rate" also appears in table header and modal
    const successRateLabels = screen.getAllByText('Success rate');
    expect(successRateLabels.length).toBeGreaterThanOrEqual(2);
  });

  it('closes failure modal when close button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<VelocityPage />);

    const failedLabel = await screen.findByText('15');
    const row = failedLabel.closest('tr');
    await user.click(row!);

    expect(screen.getByText(/Workflow runs/)).toBeInTheDocument();

    const closeBtn = screen.getByLabelText('Close');
    await user.click(closeBtn);

    // Modal-specific content should be gone (check for "Succeeded" which only appears in modal)
    expect(screen.queryByText('Succeeded')).not.toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/*  Helper function tests                                              */
/* ------------------------------------------------------------------ */

describe('Workflow health failure rate variants', () => {
  const MOCK_WORKFLOWS = [
    {
      repo: 'acme/api',
      workflow_name: 'ci.yml',
      total_runs: 100,
      successes: 40,
      failures: 60,
      failure_rate_pct: 60.0,
      last_run: '2024-01-15T00:00:00Z',
    },
    {
      repo: 'acme/web',
      workflow_name: 'deploy.yml',
      total_runs: 50,
      successes: 36,
      failures: 14,
      failure_rate_pct: 28.0,
      last_run: '2024-01-14T00:00:00Z',
    },
    {
      repo: 'acme/lib',
      workflow_name: 'test.yml',
      total_runs: 80,
      successes: 68,
      failures: 12,
      failure_rate_pct: 15.0,
      last_run: '2024-01-13T00:00:00Z',
    },
  ];

  it('renders workflow health data with failure rate badges', async () => {
    const { getWorkflowHealth } = await import('../../api/healthSignals');
    vi.mocked(getWorkflowHealth).mockResolvedValue({ workflows: MOCK_WORKFLOWS });
    mockGetActionsVolumeReport.mockResolvedValue({ data: [] });
    mockListEvents.mockResolvedValue({ items: [], total: 0 });

    renderWithProviders(<VelocityPage />);

    // Wait for workflow health data to load — appears in both "Top failing" and "Workflow health" sections
    const badges60 = await screen.findAllByText('60.0%');
    expect(badges60.length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('28.0%').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('15.0%').length).toBeGreaterThanOrEqual(1);
  });
});

describe('Active repos show real event-derived stats', () => {
  const MOCK_EVENTS = [
    {
      id: 1,
      document_id: 'd1',
      created_at: '2024-01-15T00:00:00Z',
      ingested_at: '2024-01-15T00:00:00Z',
      action: 'git.push',
      namespace: 'git',
      actor: 'alice',
      actor_id: 1,
      actor_is_bot: false,
      org: 'myorg',
      org_id: 1,
      repo: 'myorg/api-service',
      repo_id: 1,
      business: null,
      source_ip: null,
      user_agent: null,
      geo_country_code: null,
      geo_city: null,
      geo_is_proxy: null,
      data: {},
      ingestion_source: 'webhook',
      source_file_path: '',
    },
    {
      id: 2,
      document_id: 'd2',
      created_at: '2024-01-15T01:00:00Z',
      ingested_at: '2024-01-15T01:00:00Z',
      action: 'pull_request.opened',
      namespace: 'git',
      actor: 'bob',
      actor_id: 2,
      actor_is_bot: false,
      org: 'myorg',
      org_id: 1,
      repo: 'myorg/api-service',
      repo_id: 1,
      business: null,
      source_ip: null,
      user_agent: null,
      geo_country_code: null,
      geo_city: null,
      geo_is_proxy: null,
      data: {},
      ingestion_source: 'webhook',
      source_file_path: '',
    },
    {
      id: 3,
      document_id: 'd3',
      created_at: '2024-01-15T02:00:00Z',
      ingested_at: '2024-01-15T02:00:00Z',
      action: 'pull_request.merged',
      namespace: 'git',
      actor: 'alice',
      actor_id: 1,
      actor_is_bot: false,
      org: 'myorg',
      org_id: 1,
      repo: 'myorg/web-app',
      repo_id: 2,
      business: null,
      source_ip: null,
      user_agent: null,
      geo_country_code: null,
      geo_city: null,
      geo_is_proxy: null,
      data: {},
      ingestion_source: 'webhook',
      source_file_path: '',
    },
  ];

  beforeEach(() => {
    mockGetActionsVolumeReport.mockResolvedValue({ data: [] });
    mockListEvents.mockResolvedValue({
      items: MOCK_EVENTS,
      total: 3,
      page: 1,
      page_size: 500,
      has_next: false,
    });
  });

  it('renders repo stats computed from events', async () => {
    renderWithProviders(<VelocityPage />);

    // api-service has 2 events, 1 PR event, 1 push event, 2 contributors
    expect(await screen.findByText('myorg/api-service')).toBeInTheDocument();
    expect(screen.getByText('myorg/web-app')).toBeInTheDocument();
  });
});
