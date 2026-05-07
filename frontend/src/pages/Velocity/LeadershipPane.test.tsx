import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { LeadershipPane } from './LeadershipPane';

// Mock the velocity API
const mockGetLeadershipSummary = vi.fn().mockResolvedValue({
  deployment_frequency: {
    value: 2.5,
    previous_value: 2.0,
    trend_pct: 25.0,
    classification: 'elite',
  },
  lead_time: {
    value: 9.6,
    previous_value: 12.0,
    trend_pct: -20.0,
    classification: 'high',
  },
  change_failure_rate: {
    value: 3.5,
    previous_value: 5.0,
    trend_pct: -30.0,
    classification: 'elite',
  },
  mttr: {
    value: 0.8,
    previous_value: 1.2,
    trend_pct: -33.3,
    classification: 'elite',
  },
  pr_throughput: {
    value: 15.0,
    previous_value: 12.0,
    trend_pct: 25.0,
    classification: 'n/a',
  },
  active_contributors: {
    value: 8.0,
    previous_value: 7.0,
    trend_pct: 14.3,
    classification: 'n/a',
  },
  period_days: 30,
  cached_at: null,
});

const mockGetTeamComparison = vi.fn().mockResolvedValue({
  items: [
    { team: 'team-alpha', value: 3.0, classification: 'elite' },
    { team: 'team-beta', value: 1.5, classification: 'high' },
  ],
  metric: 'deploy_freq',
  period_days: 30,
  cached_at: null,
});

const mockGetShippingCadence = vi.fn().mockResolvedValue({
  items: Array.from({ length: 90 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (89 - i));
    return {
      date: d.toISOString().slice(0, 10),
      deployments: Math.floor(Math.random() * 5),
      merges: Math.floor(Math.random() * 3),
      reviews: Math.floor(Math.random() * 8),
    };
  }),
  period_days: 90,
  cached_at: null,
});

vi.mock('../../api/velocity', () => ({
  getLeadershipSummary: (...args: unknown[]) => mockGetLeadershipSummary(...args),
  getTeamComparison: (...args: unknown[]) => mockGetTeamComparison(...args),
  getShippingCadence: (...args: unknown[]) => mockGetShippingCadence(...args),
}));

// Stub chart components (ECharts + canvas not supported in jsdom)
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

describe('LeadershipPane', () => {
  /* ---------------------------------------------------------------- */
  /*  Period selector                                                    */
  /* ---------------------------------------------------------------- */

  it('renders the period selector with 3 options', () => {
    renderWithProviders(<LeadershipPane />);

    expect(screen.getByText('30 days')).toBeInTheDocument();
    expect(screen.getByText('90 days')).toBeInTheDocument();
    expect(screen.getByText('180 days')).toBeInTheDocument();
  });

  it('renders the Period label', () => {
    renderWithProviders(<LeadershipPane />);

    expect(screen.getByText('Period:')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Metric cards                                                       */
  /* ---------------------------------------------------------------- */

  it('renders all 6 metric card labels', async () => {
    renderWithProviders(<LeadershipPane />);

    expect(await screen.findByText('Deployment Frequency')).toBeInTheDocument();
    expect(screen.getByText('Lead Time for Changes')).toBeInTheDocument();
    // "Change Failure Rate" also appears as a team comparison button label
    expect(screen.getAllByText('Change Failure Rate').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Mean Time to Recovery')).toBeInTheDocument();
    expect(screen.getByText('PR Throughput')).toBeInTheDocument();
    expect(screen.getByText('Active Contributors')).toBeInTheDocument();
  });

  it('renders metric values from API data', async () => {
    renderWithProviders(<LeadershipPane />);

    expect(await screen.findByText('2.5/day')).toBeInTheDocument();
    expect(screen.getByText('9.6h')).toBeInTheDocument();
    expect(screen.getByText('3.5%')).toBeInTheDocument();
    expect(screen.getByText('0.8h')).toBeInTheDocument();
    expect(screen.getByText('15/wk')).toBeInTheDocument();
    expect(screen.getByText('8/wk')).toBeInTheDocument();
  });

  it('renders trend percentages in metric deltas', async () => {
    renderWithProviders(<LeadershipPane />);

    // Wait for data to load
    await screen.findByText('2.5/day');

    // Trend text may appear multiple times (metric card + elsewhere) — use getAllBy
    expect(screen.getAllByText(/\+25% vs prev/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/-20% vs prev/).length).toBeGreaterThanOrEqual(1);
  });

  it('renders DORA classifications in metric deltas', async () => {
    renderWithProviders(<LeadershipPane />);

    await screen.findByText('2.5/day');

    // Multiple metrics may have same classification — use getAllBy
    expect(screen.getAllByText(/★ Elite/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/▲ High/).length).toBeGreaterThanOrEqual(1);
  });

  /* ---------------------------------------------------------------- */
  /*  Charts                                                             */
  /* ---------------------------------------------------------------- */

  it('renders DORA chart titles', async () => {
    renderWithProviders(<LeadershipPane />);

    await screen.findByText('2.5/day');

    expect(screen.getByText(/Deployment Frequency & Lead Time/)).toBeInTheDocument();
    expect(screen.getByText(/Change Failure Rate & MTTR/)).toBeInTheDocument();
  });

  it('renders line area charts when data is available', async () => {
    renderWithProviders(<LeadershipPane />);

    await screen.findByText('2.5/day');

    const lineCharts = screen.getAllByTestId('line-area-chart');
    expect(lineCharts.length).toBeGreaterThanOrEqual(2);
  });

  /* ---------------------------------------------------------------- */
  /*  Team comparison                                                    */
  /* ---------------------------------------------------------------- */

  it('renders team comparison section title', async () => {
    renderWithProviders(<LeadershipPane />);

    expect(await screen.findByText('Team Comparison')).toBeInTheDocument();
  });

  it('renders metric selector buttons for team comparison', () => {
    renderWithProviders(<LeadershipPane />);

    expect(screen.getByText('Deploy Frequency')).toBeInTheDocument();
    expect(screen.getByText('Lead Time')).toBeInTheDocument();
    expect(screen.getByText('Change Failure Rate', { selector: 'button' })).toBeInTheDocument();
    expect(screen.getByText('MTTR')).toBeInTheDocument();
  });

  it('renders bar chart for team comparison when data is available', async () => {
    renderWithProviders(<LeadershipPane />);

    await screen.findByText('2.5/day');

    const barCharts = screen.getAllByTestId('bar-chart');
    expect(barCharts.length).toBeGreaterThanOrEqual(1);
  });

  /* ---------------------------------------------------------------- */
  /*  Shipping cadence                                                   */
  /* ---------------------------------------------------------------- */

  it('renders shipping cadence section title', async () => {
    renderWithProviders(<LeadershipPane />);

    expect(await screen.findByText('Shipping Cadence')).toBeInTheDocument();
  });

  it('renders contribution calendar for shipping cadence', async () => {
    renderWithProviders(<LeadershipPane />);

    await screen.findByText('2.5/day');

    const calendar = screen.getByTestId('contribution-calendar');
    expect(calendar).toBeInTheDocument();
    expect(calendar).toHaveAttribute('data-has-data', 'true');
  });

  /* ---------------------------------------------------------------- */
  /*  Period switching                                                   */
  /* ---------------------------------------------------------------- */

  it('calls API with updated period when switching', async () => {
    const user = userEvent.setup();
    renderWithProviders(<LeadershipPane />);

    await screen.findByText('2.5/day');

    const btn90 = screen.getByText('90 days');
    await user.click(btn90);

    // Verify the API was called with the new period
    expect(mockGetLeadershipSummary).toHaveBeenCalledWith({ period: 90 });
  });

  /* ---------------------------------------------------------------- */
  /*  Empty / loading states                                             */
  /* ---------------------------------------------------------------- */

  it('shows loading state metric cards before data loads', () => {
    // Reset mock to never resolve
    mockGetLeadershipSummary.mockReturnValueOnce(new Promise(() => {}));

    renderWithProviders(<LeadershipPane />);

    const loadingTexts = screen.getAllByText('Loading…');
    expect(loadingTexts.length).toBeGreaterThanOrEqual(1);
  });
});
