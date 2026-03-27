import { describe, it, expect, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { VelocityPage } from './index';

vi.mock('../../api/reports', () => ({
  getActionsVolumeReport: vi.fn().mockResolvedValue({ data: [] }),
}));

vi.mock('../../api/events', () => ({
  listEvents: vi.fn().mockResolvedValue({ items: [], total: 0 }),
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

  it('shows placeholder values for demo metrics', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('4.2 h')).toBeInTheDocument();
    expect(screen.getByText('2.8 h')).toBeInTheDocument();
    expect(screen.getByText('3.1%')).toBeInTheDocument();
    expect(screen.getByText('6.4 / d')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('74%')).toBeInTheDocument();
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

  it('renders 3 LineAreaCharts and 1 BarChart', () => {
    renderWithProviders(<VelocityPage />);

    const lineCharts = screen.getAllByTestId('line-area-chart');
    expect(lineCharts).toHaveLength(3);

    const barCharts = screen.getAllByTestId('bar-chart');
    expect(barCharts).toHaveLength(1);
  });

  it('renders chart titles for all 4 charts', () => {
    renderWithProviders(<VelocityPage />);

    // Unique chart titles (no collision with metric card labels)
    expect(screen.getByText(/Workflow success rate/)).toBeInTheDocument();
    expect(screen.getByText(/Daily deployments/)).toBeInTheDocument();
    // "Lead time for changes" and "Change failure rate" also appear as metric
    // labels and table headers. Verify at least 2 matches each (metric + chart).
    expect(screen.getAllByText(/Lead time for changes/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/Change failure rate/).length).toBeGreaterThanOrEqual(2);
  });

  it('renders "— 14 days" period labels for all charts', () => {
    renderWithProviders(<VelocityPage />);

    const periodLabels = screen.getAllByText('— 14 days');
    expect(periodLabels).toHaveLength(4);
  });

  it('passes correct series names to the lead time chart', () => {
    renderWithProviders(<VelocityPage />);

    const lineCharts = screen.getAllByTestId('line-area-chart');
    const leadTimeChart = lineCharts[0];
    const series = JSON.parse(leadTimeChart.getAttribute('data-series') ?? '[]') as { name: string }[];
    const names = series.map((s: { name: string }) => s.name);

    expect(names).toContain('Median');
    expect(names).toContain('P90');
  });

  it('passes the Deployments series to the bar chart', () => {
    renderWithProviders(<VelocityPage />);

    const barChart = screen.getByTestId('bar-chart');
    const series = JSON.parse(barChart.getAttribute('data-series') ?? '[]') as { name: string }[];

    expect(series[0].name).toBe('Deployments');
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
    // The repos table is the last one (failing workflows table may or may not render)
    const repoTable = tables[tables.length - 1];
    const headers = within(repoTable).getAllByRole('columnheader');
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

  it('renders 5 rows of repository data', () => {
    renderWithProviders(<VelocityPage />);

    const tables = screen.getAllByRole('table');
    const repoTable = tables[tables.length - 1];
    const rows = within(repoTable).getAllByRole('row');
    // 1 header row + 5 data rows
    expect(rows).toHaveLength(6);
  });

  it('renders repository names', () => {
    renderWithProviders(<VelocityPage />);

    expect(screen.getByText('octowatch/frontend')).toBeInTheDocument();
    expect(screen.getByText('octowatch/backend')).toBeInTheDocument();
    expect(screen.getByText('octowatch/infra')).toBeInTheDocument();
    expect(screen.getByText('octowatch/docs')).toBeInTheDocument();
    expect(screen.getByText('octowatch/cli')).toBeInTheDocument();
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
