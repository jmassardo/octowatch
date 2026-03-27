import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { VelocityPage } from './index';

const mockGetActionsVolumeReport = vi.fn().mockResolvedValue({ data: [] });
const mockListEvents = vi.fn().mockResolvedValue({ items: [], total: 0 });

vi.mock('../../api/reports', () => ({
  getActionsVolumeReport: (...args: unknown[]) => mockGetActionsVolumeReport(...args),
}));

vi.mock('../../api/events', () => ({
  listEvents: (...args: unknown[]) => mockListEvents(...args),
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
    // "Change failure rate" also appears in chart title
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
  /*  Most active repositories table                                    */
  /* ---------------------------------------------------------------- */

  it('renders the most active repositories section title', () => {
    renderWithProviders(<VelocityPage />);

    expect(
      screen.getByText('Most active repositories — last 30 days'),
    ).toBeInTheDocument();
  });

  it('renders the repos table with correct column headers', () => {
    renderWithProviders(<VelocityPage />);

    const tables = screen.getAllByRole('table');
    const repoTable = tables[tables.length - 1];
    const headers = within(repoTable).getAllByRole('columnheader');
    const headerTexts = headers.map((h) => h.textContent);

    expect(headerTexts).toEqual([
      'Repository',
      'Events',
      'Contributors',
    ]);
  });

  it('renders empty state when no repository data is available', () => {
    renderWithProviders(<VelocityPage />);

    expect(
      screen.getByText('No repository activity data available'),
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

  it('renders active repos derived from events', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('92.8%');

    // Repos derived from mock events
    expect(screen.getByText('myorg/api-service')).toBeInTheDocument();
    expect(screen.getByText('myorg/web-app')).toBeInTheDocument();
  });
});
