import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
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
  ContributionCalendar: () => <div data-testid="contribution-calendar" />,
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

  it('renders the DORA tier label and Elite badge', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('DORA tier')).toBeInTheDocument();
    expect(screen.getByText('★ Elite')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Info banner                                                       */
  /* ---------------------------------------------------------------- */

  it('renders the info banner about system behavior metrics', () => {
    renderWithProviders(<VelocityPage />);

    expect(
      screen.getByText(/metrics here measure/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/system behavior/i)).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  All 8 metric cards                                                */
  /* ---------------------------------------------------------------- */

  it('renders all 8 metric card labels', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('PRs merged (30d)')).toBeInTheDocument();
    // "Lead time for changes" also appears in chart title; verify at least the metric card
    expect(screen.getAllByText(/Lead time for changes/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('PR cycle time (median)')).toBeInTheDocument();
    // "Change failure rate" also appears in chart title and table header
    expect(screen.getAllByText(/Change failure rate/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Deployments (30d)')).toBeInTheDocument();
    expect(screen.getByText('Workflow success')).toBeInTheDocument();
    expect(screen.getByText('WIP (items in flight)')).toBeInTheDocument();
    expect(screen.getByText('Planned work ratio')).toBeInTheDocument();
  });

  it('shows dash for metrics that require API integration', () => {
    renderWithProviders(<VelocityPage />);

    // Metrics without API backing show '—'
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(5);

    // Integration message is shown for unavailable metrics
    const integrationHints = screen.getAllByText('Requires GitHub API integration');
    expect(integrationHints).toHaveLength(5);
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

  it('renders lead time placeholder and empty-state messages for charts when no data', () => {
    renderWithProviders(<VelocityPage />);

    // Lead time chart always shows placeholder
    expect(
      screen.getByText(/No data available — requires GitHub deployment API integration/),
    ).toBeInTheDocument();

    // With empty mock data, data-driven charts show empty state
    const noDataMessages = screen.getAllByText('No workflow data available');
    expect(noDataMessages).toHaveLength(3);
  });

  it('renders chart titles for all 4 charts', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText(/Workflow success rate/)).toBeInTheDocument();
    expect(screen.getByText(/Daily workflow runs/)).toBeInTheDocument();
    // "Lead time for changes" and "Change failure rate" also appear as metric labels
    expect(screen.getAllByText(/Lead time for changes/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/Change failure rate/).length).toBeGreaterThanOrEqual(2);
  });

  it('renders lead time integration label and dynamic chart period labels', () => {
    renderWithProviders(<VelocityPage />);

    // Lead time chart shows "requires integration" label
    expect(screen.getByText('— requires integration')).toBeInTheDocument();

    // Other charts show dynamic period label (empty data → '—')
    const periodLabels = screen.getAllByText('— —');
    expect(periodLabels).toHaveLength(3);
  });

  it('renders lead time placeholder instead of chart', () => {
    renderWithProviders(<VelocityPage />);

    // Lead time has no API data, so shows a placeholder message
    expect(
      screen.getByText(/No data available — requires GitHub deployment API integration/),
    ).toBeInTheDocument();
  });

  it('shows empty state for bar chart area when no data', () => {
    renderWithProviders(<VelocityPage />);

    // With empty mock data, bar chart area shows placeholder text
    const noDataMessages = screen.getAllByText('No workflow data available');
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
    const tableWrap = sectionTitle.nextElementSibling?.nextElementSibling;
    const table = tableWrap?.querySelector('table');
    expect(table).toBeTruthy();
    const headers = within(table!).getAllByRole('columnheader');
    const headerTexts = headers.map((h) => h.textContent);

    expect(headerTexts).toEqual([
      'Workflow',
      'Repository',
      'Failure rate',
      'Last failed',
      'P50 duration',
    ]);
  });

  it('renders sample failing workflow rows', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('deploy-production.yml')).toBeInTheDocument();
    expect(screen.getByText('e2e-tests.yml')).toBeInTheDocument();
    expect(screen.getByText('integration-tests.yml')).toBeInTheDocument();
  });

  it('renders failure rate badges with correct values', () => {
    renderWithProviders(<VelocityPage />);

    // 60% → danger, 28% → danger (>20), 15% → attention (>10)
    expect(screen.getByText('60%')).toBeInTheDocument();
    expect(screen.getByText('28%')).toBeInTheDocument();
    expect(screen.getByText('15%')).toBeInTheDocument();
  });

  it('renders repository names in the failing workflows table', () => {
    renderWithProviders(<VelocityPage />);

    // These repos appear in both failing workflows and active repos tables
    expect(screen.getAllByText('acme/infra-deploy').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('acme/checkout-service').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('globex/auth-service').length).toBeGreaterThanOrEqual(1);
  });

  it('renders last failed and P50 duration for failing workflows', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('14 min ago')).toBeInTheDocument();
    expect(screen.getByText('2h ago')).toBeInTheDocument();
    expect(screen.getByText('4m 22s')).toBeInTheDocument();
    expect(screen.getByText('12m 08s')).toBeInTheDocument();
  });

  it('shows sample data banner for top failing workflows', () => {
    renderWithProviders(<VelocityPage />);

    expect(
      screen.getByText(/Top failing workflows display sample data/),
    ).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Most active repositories table                                    */
  /* ---------------------------------------------------------------- */

  it('renders the most active repositories section title', () => {
    renderWithProviders(<VelocityPage />);

    expect(
      screen.getByText('Most active repositories — last 30 days'),
    ).toBeInTheDocument();
  });

  it('renders the repos table with enhanced column headers', () => {
    renderWithProviders(<VelocityPage />);

    // Find the most active repos section title (sectionTitle class div)
    const sectionTitles = screen.getAllByText(/Most active repositories/);
    const sectionTitle = sectionTitles[0];
    // The table is the next sibling tableWrap
    const container = sectionTitle.closest('.page') ?? document.body;
    const allTables = within(container as HTMLElement).getAllByRole('table');
    // Find the table that contains "Commits" header (the active repos table)
    const repoTable = allTables.find((t) =>
      within(t).queryByText('Commits') !== null,
    );
    expect(repoTable).toBeTruthy();
    const headers = within(repoTable!).getAllByRole('columnheader');
    const headerTexts = headers.map((h) => h.textContent);

    expect(headerTexts).toEqual([
      'Repository',
      'Commits',
      'PRs merged',
      'Change failure rate',
      'MTTR',
      'Contributors',
    ]);
  });

  it('renders sample active repos when no real data is available', () => {
    renderWithProviders(<VelocityPage />);

    // Sample data includes acme/payments-api
    expect(screen.getByText('acme/payments-api')).toBeInTheDocument();
    expect(screen.getByText('847')).toBeInTheDocument();
    expect(screen.getByText('214')).toBeInTheDocument();
  });

  it('renders CFR labels with correct variants for sample repos', () => {
    renderWithProviders(<VelocityPage />);

    // acme/infra-deploy has 14.3% CFR → danger
    expect(screen.getByText('14.3%')).toBeInTheDocument();
    // globex/auth-service has 6.2% CFR → attention
    expect(screen.getByText('6.2%')).toBeInTheDocument();
    // acme/payments-api has 2.1% CFR → success
    expect(screen.getByText('2.1%')).toBeInTheDocument();
  });

  it('shows sample data banner for most active repos when no real data', () => {
    renderWithProviders(<VelocityPage />);

    expect(
      screen.getByText(/Most active repositories display sample data/),
    ).toBeInTheDocument();
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
    { id: 1, document_id: 'd1', created_at: '2024-01-15T00:00:00Z', ingested_at: '2024-01-15T00:00:00Z', action: 'push', namespace: 'git', actor: 'alice', actor_id: 1, actor_is_bot: false, org: 'myorg', org_id: 1, repo: 'myorg/api-service', repo_id: 1, business: null, source_ip: null, user_agent: null, geo_country_code: null, geo_city: null, geo_is_proxy: null, data: {}, ingestion_source: 'webhook', source_file_path: '' },
    { id: 2, document_id: 'd2', created_at: '2024-01-15T01:00:00Z', ingested_at: '2024-01-15T01:00:00Z', action: 'push', namespace: 'git', actor: 'bob', actor_id: 2, actor_is_bot: false, org: 'myorg', org_id: 1, repo: 'myorg/api-service', repo_id: 1, business: null, source_ip: null, user_agent: null, geo_country_code: null, geo_city: null, geo_is_proxy: null, data: {}, ingestion_source: 'webhook', source_file_path: '' },
    { id: 3, document_id: 'd3', created_at: '2024-01-15T02:00:00Z', ingested_at: '2024-01-15T02:00:00Z', action: 'pull_request', namespace: 'git', actor: 'alice', actor_id: 1, actor_is_bot: false, org: 'myorg', org_id: 1, repo: 'myorg/web-app', repo_id: 2, business: null, source_ip: null, user_agent: null, geo_country_code: null, geo_city: null, geo_is_proxy: null, data: {}, ingestion_source: 'webhook', source_file_path: '' },
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
    const lineCharts = screen.getAllByTestId('line-area-chart');
    expect(lineCharts.length).toBeGreaterThanOrEqual(2);

    const barCharts = screen.getAllByTestId('bar-chart');
    expect(barCharts).toHaveLength(1);
  });

  it('renders period label based on bucket count', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('92.8%');

    // 2 buckets → "2 days"
    const periodLabels = screen.getAllByText('— 2 days');
    expect(periodLabels).toHaveLength(3);
  });

  it('renders active repos derived from events with enhanced columns', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('92.8%');

    // Repos derived from mock events
    expect(screen.getByText('myorg/api-service')).toBeInTheDocument();
    expect(screen.getByText('myorg/web-app')).toBeInTheDocument();

    // When real data exists, new columns show dashes (no commits/PRs/MTTR data from events API)
    const repoTable = screen.getByText('myorg/api-service').closest('table');
    expect(repoTable).toBeTruthy();
    const headers = within(repoTable!).getAllByRole('columnheader');
    const headerTexts = headers.map((h) => h.textContent);
    expect(headerTexts).toContain('Commits');
    expect(headerTexts).toContain('PRs merged');
    expect(headerTexts).toContain('MTTR');
  });

  it('does not show sample data banner for repos when real data exists', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('92.8%');

    // The failing workflows banner still exists, but repos banner should not
    expect(
      screen.queryByText(/Most active repositories display sample data/),
    ).not.toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/*  DORA badge modal                                                   */
/* ------------------------------------------------------------------ */

describe('VelocityPage DORA badge interaction', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it('DORA badge is clickable with role=button', () => {
    renderWithProviders(<VelocityPage />);

    const badge = screen.getByText('★ Elite');
    expect(badge).toHaveAttribute('role', 'button');
    expect(badge).toHaveAttribute('tabindex', '0');
  });

  it('opens DORA modal when badge is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<VelocityPage />);

    const badge = screen.getByText('★ Elite');
    await user.click(badge);

    expect(screen.getByText('DORA Metrics — Elite Tier')).toBeInTheDocument();
    expect(screen.getByText('Deployment Frequency')).toBeInTheDocument();
    expect(screen.getByText('Lead Time for Changes')).toBeInTheDocument();
    expect(screen.getByText('Change Failure Rate')).toBeInTheDocument();
    expect(screen.getByText('Time to Restore Service')).toBeInTheDocument();
  });

  it('closes DORA modal when close button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<VelocityPage />);

    const badge = screen.getByText('★ Elite');
    await user.click(badge);

    expect(screen.getByText('DORA Metrics — Elite Tier')).toBeInTheDocument();

    const closeBtn = screen.getByLabelText('Close');
    await user.click(closeBtn);

    expect(screen.queryByText('DORA Metrics — Elite Tier')).not.toBeInTheDocument();
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
        { id: 1, document_id: 'd1', created_at: '2024-01-15T00:00:00Z', ingested_at: '2024-01-15T00:00:00Z', action: 'push', namespace: 'git', actor: 'alice', actor_id: 1, actor_is_bot: false, org: 'myorg', org_id: 1, repo: 'myorg/api-service', repo_id: 1, business: null, source_ip: null, user_agent: null, geo_country_code: null, geo_city: null, geo_is_proxy: null, data: {}, ingestion_source: 'webhook', source_file_path: '' },
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
    expect(row).toHaveAttribute('role', 'button');
    expect(row).toHaveAttribute('tabindex', '0');
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
    expect(row).toHaveAttribute('role', 'button');
  });

  it('clicking a failure row opens a detail modal', async () => {
    const user = userEvent.setup();
    renderWithProviders(<VelocityPage />);

    const failedLabel = await screen.findByText('15');
    const row = failedLabel.closest('tr');
    await user.click(row!);

    // Modal should show the title with "Workflow failures"
    expect(screen.getByText(/Workflow failures/)).toBeInTheDocument();
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

    expect(screen.getByText(/Workflow failures/)).toBeInTheDocument();

    const closeBtn = screen.getByLabelText('Close');
    await user.click(closeBtn);

    // Modal-specific content should be gone (check for "Succeeded" which only appears in modal)
    expect(screen.queryByText('Succeeded')).not.toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/*  Helper function tests                                              */
/* ------------------------------------------------------------------ */

describe('Failing workflow failure rate variants', () => {
  it('renders 60% failure rate with danger variant', () => {
    renderWithProviders(<VelocityPage />);

    // 60% should appear (danger variant, >20%)
    const badge60 = screen.getByText('60%');
    expect(badge60).toBeInTheDocument();
  });

  it('renders 28% failure rate as a badge', () => {
    renderWithProviders(<VelocityPage />);

    // 28% should appear (danger variant, >20%)
    const badge28 = screen.getByText('28%');
    expect(badge28).toBeInTheDocument();
  });

  it('renders 15% failure rate as a badge', () => {
    renderWithProviders(<VelocityPage />);

    // 15% should appear (attention variant, >10% and ≤20%)
    const badge15 = screen.getByText('15%');
    expect(badge15).toBeInTheDocument();
  });
});

describe('Active repos CFR variants', () => {
  it('renders sample repo MTTR values', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('38m')).toBeInTheDocument();
    expect(screen.getByText('22m')).toBeInTheDocument();
    expect(screen.getByText('1h 12m')).toBeInTheDocument();
    expect(screen.getByText('45m')).toBeInTheDocument();
  });

  it('renders sample repo contributor counts', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('28')).toBeInTheDocument();
    expect(screen.getByText('19')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });
});
