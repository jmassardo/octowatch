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

// ECharts renders canvas elements that jsdom doesn't support.
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

vi.mock('./LeadershipPane', () => ({
  LeadershipPane: () => <div data-testid="leadership-pane">Leadership Pane</div>,
}));

describe('VelocityPage', () => {
  /* ---------------------------------------------------------------- */
  /*  Consolidated view (no tabs)                                       */
  /* ---------------------------------------------------------------- */

  it('does not render tab navigation (tabs have been removed)', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.queryByRole('tab')).not.toBeInTheDocument();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  });

  it('renders the LeadershipPane inline', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByTestId('leadership-pane')).toBeInTheDocument();
  });

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
      screen.getByText(/track ci\/cd throughput and development flow metrics/i),
    ).toBeInTheDocument();
  });

  it('renders the DORA tier label and pending badge when no data', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getAllByText('DORA tier').length).toBeGreaterThanOrEqual(1);
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
  /*  Removed widgets verification                                      */
  /* ---------------------------------------------------------------- */

  it('does not render the Branch Protection Changes section', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.queryByText(/Branch protection changes/)).not.toBeInTheDocument();
    expect(screen.queryByText('Protections removed')).not.toBeInTheDocument();
  });

  it('does not render the Workflow Health callout', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.queryByText('Workflow Health')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Workflow Health/i })).not.toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Workflow Trends section                                           */
  /* ---------------------------------------------------------------- */

  it('renders the Workflow Trends section title', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('Workflow Trends')).toBeInTheDocument();
  });

  it('renders empty-state messages for all charts when no data', async () => {
    renderWithProviders(<VelocityPage />);

    const noDataMessages = await screen.findAllByText('No workflow data available');
    expect(noDataMessages).toHaveLength(4);
  });

  it('renders chart titles for all 4 workflow charts', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText(/Workflow success rate/)).toBeInTheDocument();
    expect(screen.getByText(/Daily deployments \/ MTTR/)).toBeInTheDocument();
    expect(screen.getByText(/Lead time for changes/)).toBeInTheDocument();
    expect(screen.getByText(/Change failure rate/)).toBeInTheDocument();
  });

  it('renders dynamic chart period labels for all 4 charts when no data', () => {
    renderWithProviders(<VelocityPage />);

    const periodLabels = screen.getAllByText('— —');
    expect(periodLabels).toHaveLength(4);
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

    const sectionTitle = screen.getByText('Most active repositories — last 30 days');
    const tableWrap = sectionTitle.nextElementSibling;
    const table = tableWrap?.querySelector('table');
    expect(table).toBeTruthy();
    const headerRow = table!.querySelector('thead tr');
    const headers = headerRow!.querySelectorAll('th');
    const headerTexts = Array.from(headers).map((h) =>
      h.textContent?.replace(/[⇅↑↓ⓘ]/g, '').trim(),
    );

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

  /* ---------------------------------------------------------------- */
  /*  Empty state                                                       */
  /* ---------------------------------------------------------------- */

  it('renders the empty state message when no workflow data is available', async () => {
    renderWithProviders(<VelocityPage />);

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

  it('renders charts with real data when buckets are available', async () => {
    renderWithProviders(<VelocityPage />);

    // Wait for data to load
    await screen.findByText('★ Elite');

    // 3 line-area-charts: Lead time, CFR, Workflow success
    const lineCharts = screen.getAllByTestId('line-area-chart');
    expect(lineCharts.length).toBeGreaterThanOrEqual(3);

    const barCharts = screen.getAllByTestId('bar-chart');
    expect(barCharts).toHaveLength(1);
  });

  it('renders period label based on bucket count', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('★ Elite');

    // 2 buckets → "2 days" — all 4 charts show this label
    const periodLabels = screen.getAllByText('— 2 days');
    expect(periodLabels).toHaveLength(4);
  });

  it('renders active repos derived from events with activity columns', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('★ Elite');

    expect(screen.getByText('myorg/api-service')).toBeInTheDocument();
    expect(screen.getByText('myorg/web-app')).toBeInTheDocument();

    const repoTable = screen.getByText('myorg/api-service').closest('table');
    expect(repoTable).toBeTruthy();
    const headerRow = repoTable!.querySelector('thead tr');
    const headers = headerRow!.querySelectorAll('th');
    const headerTexts = Array.from(headers).map((h) =>
      h.textContent?.replace(/[⇅↑↓ⓘ]/g, '').trim(),
    );
    expect(headerTexts).toContain('Events');
    expect(headerTexts).toContain('PR events');
    expect(headerTexts).toContain('Push events');
    expect(headerTexts).toContain('Contributors');
  });

  it('renders dynamic DORA tier badge based on data', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('★ Elite');

    // Mock data has 167 succeeded / 30 days ≈ 5.6 deploys/day (Elite)
    // and CFR 7.2% (High), average = 3.5 → Elite
    expect(screen.getByText('★ Elite')).toBeInTheDocument();
  });

  it('renders MTTR chart with dual series when data is available', async () => {
    renderWithProviders(<VelocityPage />);

    await screen.findByText('★ Elite');

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

  it('repo rows have click handler', async () => {
    renderWithProviders(<VelocityPage />);

    const repoCell = await screen.findByText('myorg/api-service');
    const row = repoCell.closest('tr');
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
/*  Active repos show real event-derived stats                         */
/* ------------------------------------------------------------------ */

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

    expect(await screen.findByText('myorg/api-service')).toBeInTheDocument();
    expect(screen.getByText('myorg/web-app')).toBeInTheDocument();
  });
});
