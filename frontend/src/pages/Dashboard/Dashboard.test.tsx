import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { DashboardPage } from './index';
import { STAT_PILL_STORAGE_KEY } from '../../components/widgets/statPillConfigStorage';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockGetActionsVolumeReport = vi.fn().mockResolvedValue({
  data: [
    {
      bucket: '2024-01-01',
      workflow_runs_total: 100,
      workflow_runs_succeeded: 90,
      workflow_runs_failed: 10,
      success_rate_pct: 90,
    },
    {
      bucket: '2024-01-02',
      workflow_runs_total: 100,
      workflow_runs_succeeded: 95,
      workflow_runs_failed: 5,
      success_rate_pct: 95,
    },
  ],
});
const mockListDetections = vi.fn();
const mockListEvents = vi.fn();
const mockGetSystemHealth = vi.fn();
const mockGetUnifiedSecurity = vi.fn();
const mockGetCoverageGrowth = vi.fn();
const mockGetUnhealthyHooks = vi.fn();
const mockGetHealthScore = vi.fn();
const mockGetStalePrs = vi.fn();
const mockGetPlatformSecurity = vi.fn();
const mockGetComplianceSummary = vi.fn();
const mockGetPolicyChecks = vi.fn();
const mockGetCopilotAdoption = vi.fn();
const mockGetDevelopers = vi.fn();

vi.mock('../../api/reports', () => ({
  getActionsVolumeReport: (...args: unknown[]) => mockGetActionsVolumeReport(...args),
}));

vi.mock('../../api/detections', () => ({
  listDetections: (...args: unknown[]) => mockListDetections(...args),
}));

vi.mock('../../api/events', () => ({
  listEvents: (...args: unknown[]) => mockListEvents(...args),
}));

vi.mock('../../api/healthSignals', () => ({
  getSystemHealth: (...args: unknown[]) => mockGetSystemHealth(...args),
  getUnifiedSecurity: (...args: unknown[]) => mockGetUnifiedSecurity(...args),
  getCoverageGrowth: (...args: unknown[]) => mockGetCoverageGrowth(...args),
  getUnhealthyHooks: (...args: unknown[]) => mockGetUnhealthyHooks(...args),
  getHealthScore: (...args: unknown[]) => mockGetHealthScore(...args),
  getStalePrs: (...args: unknown[]) => mockGetStalePrs(...args),
  getPlatformSecurity: (...args: unknown[]) => mockGetPlatformSecurity(...args),
}));

vi.mock('../../api/compliance', () => ({
  getComplianceSummary: (...args: unknown[]) => mockGetComplianceSummary(...args),
  getPolicyChecks: (...args: unknown[]) => mockGetPolicyChecks(...args),
}));

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotAdoption: (...args: unknown[]) => mockGetCopilotAdoption(...args),
}));

vi.mock('../../api/devActivity', () => ({
  getDevelopers: (...args: unknown[]) => mockGetDevelopers(...args),
}));

describe('DashboardPage', () => {
  beforeEach(() => {
    localStorage.clear();
    mockNavigate.mockClear();

    mockListDetections.mockImplementation((params?: { severity?: string; status?: string }) => {
      if (params?.severity === 'critical') {
        return Promise.resolve({ items: [], total: 2, page: 1, page_size: 100, has_next: false });
      }
      if (params?.status === 'investigating') {
        return Promise.resolve({ items: [], total: 4, page: 1, page_size: 100, has_next: false });
      }
      return Promise.resolve({
        items: [
          {
            id: 1,
            rule_id: 1,
            rule_name: 'Suspicious login',
            rule_version: 1,
            severity: 'high',
            confidence: 'high',
            confidence_score: 0.9,
            status: 'investigating',
            title: 'Suspicious login',
            description: '',
            actor: 'alice',
            org: 'octowatch',
            repo: 'repo',
            source_ip: null,
            window_start: null,
            window_end: null,
            event_ids: [],
            context_data: {},
            triggered_at: '2024-01-02T00:00:00Z',
            assigned_to: null,
            resolved_at: null,
            resolution_note: null,
            tickets: [],
          },
        ],
        total: 6,
        page: 1,
        page_size: 100,
        has_next: false,
      });
    });

    mockListEvents.mockResolvedValue({
      items: [
        {
          id: 1,
          created_at: '2024-01-02T10:00:00Z',
          actor: 'alice',
          org: 'octowatch',
          repo: 'a',
          action: 'pull_request.opened',
        },
        {
          id: 2,
          created_at: '2024-01-02T09:00:00Z',
          actor: 'bob',
          org: 'octowatch',
          repo: 'b',
          action: 'workflow_run.completed',
        },
        {
          id: 3,
          created_at: '2024-01-02T08:00:00Z',
          actor: 'chris',
          org: 'acme',
          repo: 'c',
          action: 'push',
        },
      ],
      total: 1500,
      page: 1,
      page_size: 500,
      has_next: true,
    });

    mockGetSystemHealth.mockResolvedValue({
      gap_detected: false,
      gap_duration_minutes: null,
      last_event_at: new Date(Date.now() - 4 * 60_000).toISOString(),
    });
    mockGetUnifiedSecurity.mockResolvedValue({
      secret_scanning: { open: 3, resolved: 10, total: 13, bypassed_open: 0 },
      code_scanning: { open: 1, critical: 0, high: 1, medium: 0, low: 0, total: 1 },
      dependabot: {
        open: 2,
        critical: 0,
        high: 1,
        medium: 1,
        low: 0,
        total: 2,
        critical_aging_gt_90d: 0,
      },
      detections: { active: 6, critical: 2, high: 2, medium: 1, low: 1 },
      trend_30d: [
        { day: '2024-01-01', secret_scanning: 2, code_scanning: 1, dependabot: 2 },
        { day: '2024-01-02', secret_scanning: 3, code_scanning: 1, dependabot: 2 },
      ],
    });
    mockGetCoverageGrowth.mockResolvedValue({
      total_repos: 10,
      feature_coverage: { ghas: { repos: 8, pct: 80 } },
      time_series: [
        {
          date: '2024-01-01',
          ghas_pct: 75,
          code_scanning_pct: 70,
          secret_scanning_pct: 72,
          dependabot_pct: 65,
          push_protection_pct: 60,
          ghas_repos: 7,
          code_scanning_repos: 7,
          secret_scanning_repos: 7,
          dependabot_repos: 6,
          push_protection_repos: 6,
        },
        {
          date: '2024-01-02',
          ghas_pct: 80,
          code_scanning_pct: 75,
          secret_scanning_pct: 72,
          dependabot_pct: 70,
          push_protection_pct: 60,
          ghas_repos: 8,
          code_scanning_repos: 8,
          secret_scanning_repos: 7,
          dependabot_repos: 7,
          push_protection_repos: 6,
        },
      ],
      uncovered_repos: [],
    });
    mockGetUnhealthyHooks.mockResolvedValue({
      unhealthy_hooks: [
        {
          org: 'octowatch',
          repo: 'repo',
          action: 'webhook.disabled',
          actor: 'svc',
          hook_id: '1',
          app_name: null,
          config_url: null,
          created_at: '2024-01-02T00:00:00Z',
        },
      ],
    });
    mockGetHealthScore.mockResolvedValue({
      score: 88,
      grade: 'B',
      critical_count: 1,
      high_count: 1,
      medium_count: 1,
      low_count: 1,
      total_signals: 4,
      orgs_monitored: 2,
    });
    mockGetStalePrs.mockResolvedValue({
      stale_prs: [
        {
          org: 'octowatch',
          repo: 'repo',
          pr_number: '12',
          title: 'Refactor',
          actor: 'alice',
          opened_at: '2024-01-01T00:00:00Z',
          days_open: 2,
        },
      ],
    });
    mockGetPlatformSecurity.mockResolvedValue({
      orgs: [
        {
          org: 'octowatch',
          sso_configured: true,
          two_fa_required: true,
          audit_log_streaming: true,
          ip_allowlist_configured: true,
          branch_protection_default: true,
          compliance_score: 92,
          recommendations: [],
        },
        {
          org: 'acme',
          sso_configured: true,
          two_fa_required: true,
          audit_log_streaming: true,
          ip_allowlist_configured: false,
          branch_protection_default: false,
          compliance_score: 78,
          recommendations: [],
        },
      ],
      overall_compliance_score: 85,
    });
    mockGetComplianceSummary.mockResolvedValue({
      overall_score: 85,
      frameworks_tracked: 4,
      controls_passing: 120,
      controls_total: 140,
      critical_gaps: 2,
      last_assessment_date: '2024-01-02T00:00:00Z',
      frameworks: [],
    });
    mockGetPolicyChecks.mockResolvedValue({
      checks: [],
      last_run: '2024-01-02T00:00:00Z',
      checks_passing: 9,
      checks_total: 12,
    });
    mockGetCopilotAdoption.mockResolvedValue({
      tiers: [],
      total_adoption: 61,
      power_users: [],
      feature_adoption: [
        { feature: 'chat', active_users: 10, total_seats: 20, pct: 50, trend_7d: 4, color: '#000' },
        {
          feature: 'completions',
          active_users: 15,
          total_seats: 20,
          pct: 75,
          trend_7d: 2,
          color: '#111',
        },
      ],
      minimal_users: [],
    });
    mockGetDevelopers.mockResolvedValue({
      developers: [
        {
          login: 'alice',
          event_count: 10,
          pr_count: 2,
          review_count: 4,
          top_repos: ['a'],
          repo_count: 1,
          last_active: '2024-01-02T00:00:00Z',
          weekly_counts: [1, 2, 3],
        },
        {
          login: 'bob',
          event_count: 8,
          pr_count: 1,
          review_count: 2,
          top_repos: ['b'],
          repo_count: 1,
          last_active: '2024-01-02T00:00:00Z',
          weekly_counts: [1, 1, 2],
        },
        {
          login: 'chris',
          event_count: 6,
          pr_count: 1,
          review_count: 1,
          top_repos: ['c'],
          repo_count: 1,
          last_active: '2024-01-02T00:00:00Z',
          weekly_counts: [1, 1, 1],
        },
      ],
      lookback_days: 30,
    });
  });

  it('renders default customizable pills and platform alerts', async () => {
    renderWithProviders(<DashboardPage />);

    expect(await screen.findByTestId('stat-pill-open-detections')).toBeInTheDocument();
    expect(screen.getByTestId('stat-pill-compliance-score')).toBeInTheDocument();
    expect(screen.getByText(/92\.5% success/)).toBeInTheDocument();
    expect(screen.getByText(/1.5K events/)).toBeInTheDocument();
  });

  it('opens the configure drawer and persists changes', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    await user.click(screen.getByRole('button', { name: /Configure stat pills/i }));
    expect(screen.getByRole('dialog', { name: /Configure stat pills/i })).toBeInTheDocument();

    await user.click(screen.getAllByRole('checkbox')[0]!);
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(screen.queryByTestId('stat-pill-open-detections')).not.toBeInTheDocument();
    expect(localStorage.getItem(STAT_PILL_STORAGE_KEY)).toContain('secret-alerts');
  });

  it('loads saved pill configuration from localStorage', async () => {
    localStorage.setItem(
      STAT_PILL_STORAGE_KEY,
      JSON.stringify({
        enabledPills: ['secret-alerts'],
        order: ['secret-alerts', 'open-detections'],
        thresholds: {},
      }),
    );

    renderWithProviders(<DashboardPage />);

    expect(await screen.findByTestId('stat-pill-secret-alerts')).toBeInTheDocument();
    expect(screen.queryByTestId('stat-pill-open-detections')).not.toBeInTheDocument();
  });

  it('renders the ingestion banner when a sync gap exists', async () => {
    mockGetSystemHealth.mockResolvedValueOnce({
      gap_detected: true,
      gap_duration_minutes: 45,
      last_event_at: new Date(Date.now() - 45 * 60_000).toISOString(),
    });

    renderWithProviders(<DashboardPage />);

    expect(await screen.findByText(/Data ingestion gap detected/)).toBeInTheDocument();
  });

  it('keeps platform alert navigation clickable', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DashboardPage />);

    await user.click(await screen.findByLabelText(/185 succeeded — view velocity/i));
    await user.click(screen.getByLabelText(/1.5K events — view all events/i));

    expect(mockNavigate).toHaveBeenCalledWith('/velocity');
    expect(mockNavigate).toHaveBeenCalledWith('/events');
  });
});
