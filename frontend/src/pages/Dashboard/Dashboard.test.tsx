import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { DashboardPage } from './index';

const mockGetActionsVolumeReport = vi.fn().mockResolvedValue({ data: [] });
const mockListDetections = vi.fn().mockResolvedValue({ items: [], total: 0 });
const mockListEvents = vi.fn().mockResolvedValue({ items: [], total: 0 });

vi.mock('../../api/reports', () => ({
  getActionsVolumeReport: (...args: unknown[]) => mockGetActionsVolumeReport(...args),
}));

vi.mock('../../api/detections', () => ({
  listDetections: (...args: unknown[]) => mockListDetections(...args),
}));

vi.mock('../../api/events', () => ({
  listEvents: (...args: unknown[]) => mockListEvents(...args),
}));

vi.mock('../../components/charts/ContributionCalendar', () => ({
  ContributionCalendar: () => <div data-testid="contribution-calendar" />,
}));

describe('DashboardPage', () => {
  /* ---------------------------------------------------------------- */
  /*  Page header                                                      */
  /* ---------------------------------------------------------------- */

  it('renders the page title', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.getByText('Dashboard')).toBeInTheDocument();
  });

  it('renders the page subtitle', () => {
    renderWithProviders(<DashboardPage />);

    expect(
      screen.getByText(/activity across your organizations/i),
    ).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Stat pills                                                       */
  /* ---------------------------------------------------------------- */

  it('renders all stat pill labels', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.getByText(/events today/)).toBeInTheDocument();
    expect(screen.getByText(/open threats/)).toBeInTheDocument();
    expect(screen.getByText(/pipeline success/)).toBeInTheDocument();
    expect(screen.getByText(/active devs/)).toBeInTheDocument();
    expect(screen.getByText(/total events/)).toBeInTheDocument();
  });

  it('shows dash for pipeline success when no data', () => {
    renderWithProviders(<DashboardPage />);

    // With empty mock data, workflowSuccessRate is null → '—'
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it('does not show hardcoded "94.2%" or "1.8M"', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.queryByText('94.2%')).not.toBeInTheDocument();
    expect(screen.queryByText('1.8M')).not.toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Platform alerts                                                   */
  /* ---------------------------------------------------------------- */

  it('renders dynamic platform alerts with real labels', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.getByText(/Workflow runs:/)).toBeInTheDocument();
    expect(screen.getByText(/Events volume:/)).toBeInTheDocument();
    expect(screen.getByText(/Active detections:/)).toBeInTheDocument();
  });

  it('does not render hardcoded alert text', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.queryByText(/Workflow failure rate.*\+12%/)).not.toBeInTheDocument();
    expect(screen.queryByText(/PR cycle time.*platform-team/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Deploy frequency.*\+28%/)).not.toBeInTheDocument();
  });

  it('shows zero values in alerts when no data is available', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.getByText('0 succeeded')).toBeInTheDocument();
    expect(screen.getByText('0 failed')).toBeInTheDocument();
    expect(screen.getByText('0 investigating')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Activity heatmap                                                  */
  /* ---------------------------------------------------------------- */

  it('renders the contribution calendar', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.getByTestId('contribution-calendar')).toBeInTheDocument();
  });

  /* ---------------------------------------------------------------- */
  /*  Severity card                                                     */
  /* ---------------------------------------------------------------- */

  it('renders the open threats severity card', async () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.getByText('Open threats by severity')).toBeInTheDocument();
    expect(await screen.findByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
    expect(screen.getByText('Medium')).toBeInTheDocument();
    expect(screen.getByText('Low')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/*  Tests with populated API data                                      */
/* ------------------------------------------------------------------ */

describe('DashboardPage with data', () => {
  const MOCK_BUCKETS = [
    {
      bucket: '2024-01-15',
      workflow_runs_total: 200,
      workflow_runs_succeeded: 190,
      workflow_runs_failed: 10,
      success_rate_pct: 95.0,
      unique_workflows: 5,
    },
  ];

  beforeEach(() => {
    mockGetActionsVolumeReport.mockResolvedValue({
      report_type: 'actions-volume',
      org: null,
      granularity: 'daily',
      window_days: 7,
      generated_at: '2024-01-16T00:00:00Z',
      data: MOCK_BUCKETS,
    });
    mockListDetections.mockResolvedValue({
      items: [
        { id: 1, rule_id: 1, rule_name: 'Test Rule', rule_version: 1, severity: 'critical', confidence: 'high', confidence_score: 0.95, status: 'investigating', title: 'Test', description: '', actor: null, org: 'org', repo: null, source_ip: null, window_start: null, window_end: null, event_ids: [1], context_data: {}, triggered_at: '2024-01-15T00:00:00Z', assigned_to: null, resolved_at: null, resolution_note: null, tickets: [] },
      ],
      total: 1,
      page: 1,
      page_size: 100,
      has_next: false,
    });
    mockListEvents.mockResolvedValue({
      items: [],
      total: 1500,
      page: 1,
      page_size: 500,
      has_next: true,
    });
  });

  it('renders workflow success rate from API data', async () => {
    renderWithProviders(<DashboardPage />);

    // 190/200 = 95.0%
    expect(await screen.findByText('95.0%')).toBeInTheDocument();
  });

  it('renders formatted total events count', async () => {
    renderWithProviders(<DashboardPage />);

    // 1500 → "1.5K"
    expect(await screen.findByText('1.5K')).toBeInTheDocument();
  });

  it('renders workflow alert with real counts', async () => {
    renderWithProviders(<DashboardPage />);

    expect(await screen.findByText('190 succeeded')).toBeInTheDocument();
    expect(screen.getByText('10 failed')).toBeInTheDocument();
  });

  it('renders open threats count in alerts', async () => {
    renderWithProviders(<DashboardPage />);

    expect(await screen.findByText('1 investigating')).toBeInTheDocument();
  });

  it('renders events volume in alerts', async () => {
    renderWithProviders(<DashboardPage />);

    // calendarEvents total = 1500 → "1.5K events"
    expect(await screen.findByText(/1\.5K events/)).toBeInTheDocument();
  });
});
