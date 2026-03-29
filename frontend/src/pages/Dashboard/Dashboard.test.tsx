import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { DashboardPage } from './index';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

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

const mockGetExtendedHealthSummary = vi.fn().mockResolvedValue({
  stale_repos: 0,
  pat_no_expiry: 0,
  pat_stale: 0,
  bypass_offenders: 0,
  ext_collab_total: 0,
  ext_collab_elevated: 0,
  unresolved_secret_alerts: 0,
  security_feature_disables_7d: 0,
});

const mockGetSystemHealth = vi.fn().mockResolvedValue({
  ingestion_healthy: true,
  last_event_at: '2025-03-15T00:00:00Z',
  gap_detected: false,
  gap_duration_minutes: null,
});

vi.mock('../../api/healthSignals', () => ({
  getExtendedHealthSummary: (...args: unknown[]) => mockGetExtendedHealthSummary(...args),
  getSystemHealth: (...args: unknown[]) => mockGetSystemHealth(...args),
}));

describe('DashboardPage', () => {
  /* ---------------------------------------------------------------- */
  /*  Page header                                                      */
  /* ---------------------------------------------------------------- */

  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it('renders the page title', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.getByText(/Dashboard/)).toBeInTheDocument();
  });

  it('renders the page subtitle with last synced time', async () => {
    renderWithProviders(<DashboardPage />);

    // systemHealth resolves asynchronously with last_event_at
    expect(
      await screen.findByText(/last synced:/i),
    ).toBeInTheDocument();
  });

  it('shows fallback subtitle when no system health data', () => {
    mockGetSystemHealth.mockResolvedValue({
      gap_detected: false,
      gap_duration_minutes: null,
      last_event_at: null,
    });
    renderWithProviders(<DashboardPage />);

    expect(screen.getByText(/activity across your organizations/i)).toBeInTheDocument();
  });

  it('shows org label in page title', () => {
    renderWithProviders(<DashboardPage />);

    // Default org context is empty string → "All organizations"
    expect(screen.getByText(/All organizations/)).toBeInTheDocument();
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
    expect(screen.getByText(/API calls \(24h\)/)).toBeInTheDocument();
    expect(screen.getByText(/total events/)).toBeInTheDocument();
    expect(screen.getByText(/unresolved secrets/)).toBeInTheDocument();
    expect(screen.getByText(/feature disables \(7d\)/)).toBeInTheDocument();
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
  /*  Ingestion banner                                                  */
  /* ---------------------------------------------------------------- */

  it('does not render ingestion banner when no gap detected', () => {
    renderWithProviders(<DashboardPage />);
    expect(screen.queryByText(/Data ingestion gap detected/)).not.toBeInTheDocument();
  });

  it('renders ingestion banner when gap is detected', async () => {
    mockGetSystemHealth.mockResolvedValue({
      ingestion_healthy: false,
      last_event_at: '2025-03-15T00:00:00Z',
      gap_detected: true,
      gap_duration_minutes: 45,
    });
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText(/Data ingestion gap detected/)).toBeInTheDocument();
    expect(screen.getByText(/45 minutes of missing data/)).toBeInTheDocument();
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

/* ------------------------------------------------------------------ */
/*  Severity row navigation                                            */
/* ------------------------------------------------------------------ */

describe('DashboardPage severity row clicks', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockGetActionsVolumeReport.mockResolvedValue({ data: [] });
    mockListDetections.mockResolvedValue({
      items: [
        { id: 1, rule_id: 1, rule_name: 'R1', rule_version: 1, severity: 'critical', confidence: 'high', confidence_score: 0.9, status: 'investigating', title: 'T1', description: '', actor: null, org: 'o', repo: null, source_ip: null, window_start: null, window_end: null, event_ids: [], context_data: {}, triggered_at: '2024-01-15T00:00:00Z', assigned_to: null, resolved_at: null, resolution_note: null, tickets: [] },
        { id: 2, rule_id: 2, rule_name: 'R2', rule_version: 1, severity: 'high', confidence: 'medium', confidence_score: 0.7, status: 'investigating', title: 'T2', description: '', actor: null, org: 'o', repo: null, source_ip: null, window_start: null, window_end: null, event_ids: [], context_data: {}, triggered_at: '2024-01-15T00:00:00Z', assigned_to: null, resolved_at: null, resolution_note: null, tickets: [] },
      ],
      total: 2,
      page: 1,
      page_size: 100,
      has_next: false,
    });
    mockListEvents.mockResolvedValue({ items: [], total: 0 });
  });

  it('severity rows have role=button and are clickable', async () => {
    renderWithProviders(<DashboardPage />);

    await screen.findByText('Critical');

    const criticalRow = screen.getByLabelText(/critical threats/i);
    expect(criticalRow).toHaveAttribute('role', 'button');
    expect(criticalRow).toHaveAttribute('tabindex', '0');
  });

  it('clicking Critical severity navigates to /threats?severity=critical', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    await screen.findByText('Critical');

    const criticalRow = screen.getByLabelText(/critical threats/i);
    await user.click(criticalRow);

    expect(mockNavigate).toHaveBeenCalledWith('/threats?severity=critical');
  });

  it('clicking High severity navigates to /threats?severity=high', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    await screen.findByText('High');

    const highRow = screen.getByLabelText(/high threats/i);
    await user.click(highRow);

    expect(mockNavigate).toHaveBeenCalledWith('/threats?severity=high');
  });
});

/* ------------------------------------------------------------------ */
/*  Platform alerts clickable values                                   */
/* ------------------------------------------------------------------ */

describe('DashboardPage platform alerts clicks', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockGetActionsVolumeReport.mockResolvedValue({
      data: [{
        bucket: '2024-01-15',
        workflow_runs_total: 100,
        workflow_runs_succeeded: 90,
        workflow_runs_failed: 10,
        success_rate_pct: 90.0,
        unique_workflows: 5,
      }],
    });
    mockListDetections.mockResolvedValue({
      items: [{ id: 1, rule_id: 1, rule_name: 'R', rule_version: 1, severity: 'high', confidence: 'high', confidence_score: 0.9, status: 'investigating', title: 'T', description: '', actor: null, org: 'o', repo: null, source_ip: null, window_start: null, window_end: null, event_ids: [], context_data: {}, triggered_at: '2024-01-15T00:00:00Z', assigned_to: null, resolved_at: null, resolution_note: null, tickets: [] }],
      total: 1,
      page: 1,
      page_size: 100,
      has_next: false,
    });
    mockListEvents.mockResolvedValue({ items: [], total: 500 });
  });

  it('workflow succeeded count is clickable and navigates to /velocity', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    const succeededLink = await screen.findByLabelText(/90 succeeded.*velocity/i);
    await user.click(succeededLink);

    expect(mockNavigate).toHaveBeenCalledWith('/velocity');
  });

  it('workflow failed count is clickable and navigates to /velocity', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    const failedLink = await screen.findByLabelText(/10 failed.*velocity/i);
    await user.click(failedLink);

    expect(mockNavigate).toHaveBeenCalledWith('/velocity');
  });

  it('events volume count is clickable and navigates to /events', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    const eventsLink = await screen.findByLabelText(/events.*view all events/i);
    await user.click(eventsLink);

    expect(mockNavigate).toHaveBeenCalledWith('/events');
  });

  it('investigating count is clickable and navigates to /threats', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    const threatsLink = await screen.findByLabelText(/1 investigating.*threats/i);
    await user.click(threatsLink);

    expect(mockNavigate).toHaveBeenCalledWith('/threats');
  });

  it('clickable values have proper accessibility attributes', async () => {
    renderWithProviders(<DashboardPage />);

    const succeededLink = await screen.findByLabelText(/90 succeeded.*velocity/i);
    expect(succeededLink).toHaveAttribute('role', 'button');
    expect(succeededLink).toHaveAttribute('tabindex', '0');
  });
});
