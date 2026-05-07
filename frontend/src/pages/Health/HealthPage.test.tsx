import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { HealthPage } from './index';

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts-mock" />,
}));

vi.mock('../../api/reports', () => ({
  getSeatUtilizationReport: vi.fn().mockResolvedValue({ data: [] }),
  getCopilotSeatsReport: vi.fn().mockResolvedValue({ data: [] }),
}));

vi.mock('../../api/healthSignals', () => ({
  getHealthSummary: vi.fn().mockResolvedValue({
    stale_repos: 12,
    pat_no_expiry: 5,
    pat_stale: 3,
    bypass_offenders: 7,
    ext_collab_total: 23,
    ext_collab_elevated: 4,
  }),
  getHealthScore: vi.fn().mockResolvedValue({
    score: 72,
    grade: 'C',
    critical_count: 2,
    high_count: 3,
    medium_count: 5,
    low_count: 8,
    total_signals: 18,
    orgs_monitored: 3,
  }),
  getRepoHealth: vi.fn().mockResolvedValue({
    stale: [
      {
        org: 'acme',
        repo: 'test-repo',
        last_event_at: '2024-01-01T00:00:00Z',
        days_since_activity: 200,
      },
    ],
    archived: [],
    abandoned_forks: [],
  }),
  getPatHealth: vi.fn().mockResolvedValue({
    summary: { no_expiry_count: 5, expired_count: 2, stale_90d_count: 3 },
    tokens: [],
    dormant: [],
  }),
  getBypassOffenders: vi.fn().mockResolvedValue({ offenders: [] }),
  getExternalCollaborators: vi.fn().mockResolvedValue({
    summary: { total_active: 0, org_level_count: 0, elevated_count: 0, dormant_count: 0 },
    collaborators: [],
  }),
  getDormantCollaborators: vi.fn().mockResolvedValue({ dormant: [] }),
  getSecurityPosture: vi.fn().mockResolvedValue({
    repos_with_secret_scanning: 0,
    repos_with_dependabot: 0,
    repos_with_codeql: 0,
    repos_with_ghas: 0,
    features_disabled_count: 0,
  }),
  getSecretScanning: vi.fn().mockResolvedValue({
    unresolved_total: 0,
    publicly_leaked: 0,
    open_gt_7d: 0,
    open_gt_30d: 0,
    mttr_hours: 0,
  }),
  getSsoHealth: vi.fn().mockResolvedValue({ orgs: [] }),
  getPrivilegeChanges: vi.fn().mockResolvedValue({
    admin_promotions: 0,
    integration_manager_grants: 0,
    custom_role_changes: 0,
  }),
  getAppGovernance: vi.fn().mockResolvedValue({
    apps_installed: 0,
    apps_removed: 0,
    oauth_approved: 0,
    oauth_denied: 0,
    token_revocations: 0,
    webhooks_created: 0,
    webhooks_removed: 0,
    webhooks_modified: 0,
  }),
  getCodeScanning: vi.fn().mockResolvedValue({
    total_alerts: 0,
    avg_hours_to_close: 0,
    dismissed_count: 0,
    reappeared_count: 0,
  }),
  getVulnerabilities: vi.fn().mockResolvedValue({
    total_open: 0,
    critical_open: 0,
    high_open: 0,
    open_gt_30d: 0,
    critical_open_gt_14d: 0,
    avg_open_days: 0,
  }),
  getWorkflowHealth: vi.fn().mockResolvedValue({ workflows: [] }),
  getBranchProtection: vi.fn().mockResolvedValue({
    protections_removed: 0,
    policy_overrides: 0,
    modified: 0,
    distinct_repos_affected: 0,
  }),
  getCopilotGovernance: vi.fn().mockResolvedValue({
    seats_granted_90d: 0,
    seats_removed: 0,
    unique_users: 0,
  }),
  getCodespaces: vi.fn().mockResolvedValue({
    active_never_suspended: 0,
    large_machine_count: 0,
    unique_users: 0,
  }),
  getRunnerHealth: vi.fn().mockResolvedValue({ runners: [] }),
  getGhostMembers: vi.fn().mockResolvedValue({ ghost_members: [] }),
  getStalePrs: vi.fn().mockResolvedValue({ stale_prs: [] }),
  getUnhealthyHooks: vi.fn().mockResolvedValue({ unhealthy_hooks: [] }),
  getSkippedWorkflows: vi.fn().mockResolvedValue({ skipped_workflows: [] }),
  getWafFindings: vi.fn().mockResolvedValue({ findings: [] }),
  getHealthSettings: vi.fn().mockResolvedValue({}),
  updateHealthSettings: vi.fn().mockResolvedValue({}),
  getApiAbuseSignals: vi.fn().mockResolvedValue({ signals: [] }),
  getDormantUsers: vi.fn().mockResolvedValue({
    users: [],
    summary: { total_dormant: 0, estimated_monthly_waste: 0 },
  }),
  getPlatformSecurity: vi.fn().mockResolvedValue({
    orgs: [],
    overall_compliance_score: 0,
  }),
  getMaintenanceSignals: vi.fn().mockResolvedValue({
    stale_repos: [],
    empty_repos: [],
    archived_candidates: [],
    summary: { stale_count: 0, empty_count: 0, archived_candidate_count: 0 },
  }),
}));

function renderPage(initialTab = 'repos') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/health/${initialTab}`]}>
        <Routes>
          <Route path="/health/:tab" element={<HealthPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('HealthPage', () => {
  it('renders page title and subtitle', () => {
    renderPage();
    expect(screen.getByText('Org Health')).toBeInTheDocument();
    expect(
      screen.getByText(/Monitor organization health signals and configuration drift/),
    ).toBeInTheDocument();
  });

  it('renders the tab bar with 12 tabs', () => {
    renderPage();
    const tablist = screen.getByRole('tablist');
    const tabs = within(tablist).getAllByRole('tab');
    expect(tabs).toHaveLength(12);
  });

  it('shows Repository Health pane by default', async () => {
    renderPage();
    const repoTab = screen.getByRole('tab', { name: /Repository Health/ });
    expect(repoTab).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText(/Additional repository health data/)).toBeInTheDocument();
  });

  it('switches to Access & Identity tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Access & Identity/ }));
    const accessTab = screen.getByRole('tab', { name: /Access & Identity/ });
    expect(accessTab).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText('PAT health snapshot')).toBeInTheDocument();
  });

  it('switches to License Health tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /License Health/ }));
    const licenseTab = screen.getByRole('tab', { name: /License Health/ });
    expect(licenseTab).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText('Total seats (GitHub)')).toBeInTheDocument();
  });

  it('switches to Maintenance Signals tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Maintenance Signals/ }));
    const maintenanceTab = screen.getByRole('tab', { name: /Maintenance Signals/ });
    expect(maintenanceTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getAllByText(/Stale PRs/i).length).toBeGreaterThanOrEqual(1);
  });

  it('switches to WAF Insights tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /WAF Insights/ }));
    const wafTab = screen.getByRole('tab', { name: /WAF Insights/ });
    expect(wafTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getAllByText(/Well-Architected Framework/i).length).toBeGreaterThanOrEqual(1);
  });

  it('switches to Security Posture tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Security Posture/ }));
    const tab = screen.getByRole('tab', { name: /Security Posture/ });
    expect(tab).toHaveAttribute('aria-selected', 'true');
    expect(
      await screen.findByText(/Repository-level security feature adoption/i),
    ).toBeInTheDocument();
  });

  it('switches to App Governance tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /App Governance/ }));
    const tab = screen.getByRole('tab', { name: /App Governance/ });
    expect(tab).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText(/OAuth & app summary/i)).toBeInTheDocument();
  });

  it('switches to Operations tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Operations/ }));
    const tab = screen.getByRole('tab', { name: /Operations/ });
    expect(tab).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText(/Per-workflow run metrics derived from/i)).toBeInTheDocument();
  });

  it('can switch back to Repository Health after navigating to another tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Access & Identity/ }));
    const accessTab = screen.getByRole('tab', { name: /Access & Identity/ });
    expect(accessTab).toHaveAttribute('aria-selected', 'true');

    await user.click(screen.getByRole('tab', { name: /Repository Health/ }));
    const repoTab = screen.getByRole('tab', { name: /Repository Health/ });
    expect(repoTab).toHaveAttribute('aria-selected', 'true');
  });

  it('renders health score metric cards', async () => {
    renderPage();
    expect(await screen.findByText('Health Score')).toBeInTheDocument();
    expect(screen.getByText('Total Signals')).toBeInTheDocument();
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('Orgs Monitored')).toBeInTheDocument();
  });

  it('switches to API & Abuse tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /API & Abuse/ }));
    const tab = screen.getByRole('tab', { name: /API & Abuse/ });
    expect(tab).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText(/No API abuse signals detected/)).toBeInTheDocument();
  });

  it('switches to Users tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /^Users$/ }));
    const tab = screen.getByRole('tab', { name: /^Users$/ });
    expect(tab).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText(/Inactivity threshold/)).toBeInTheDocument();
  });

  it('switches to Security tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /^Security$/ }));
    const tab = screen.getByRole('tab', { name: /^Security$/ });
    expect(tab).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText(/No platform security data available/)).toBeInTheDocument();
  });

  it('switches to Maintenance tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /^Maintenance$/ }));
    const tab = screen.getByRole('tab', { name: /^Maintenance$/ });
    expect(tab).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText(/No maintenance issues detected/)).toBeInTheDocument();
  });
});
