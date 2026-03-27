import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HealthPage } from './index';

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

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
  getRepoHealth: vi.fn().mockResolvedValue({
    stale: [
      { org: 'acme', repo: 'test-repo', last_event_at: '2024-01-01T00:00:00Z', days_since_activity: 200 },
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
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <HealthPage />
    </QueryClientProvider>,
  );
}

describe('HealthPage', () => {
  it('renders page title and subtitle', () => {
    renderPage();
    expect(screen.getByText('Org Health')).toBeInTheDocument();
    expect(
      screen.getByText(
        /Audit-log-derived health signals across repositories, access, licenses/,
      ),
    ).toBeInTheDocument();
  });

  it('renders the data source info banner', () => {
    renderPage();
    expect(
      screen.getByText(
        /Health signals are derived exclusively from GitHub audit log events/,
      ),
    ).toBeInTheDocument();
  });

  it('renders metric cards with summary data', async () => {
    renderPage();
    expect(await screen.findByText('12')).toBeInTheDocument();
    expect(screen.getByText('Stale Repos')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('PATs Without Expiry')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('Bypass Offenders')).toBeInTheDocument();
    expect(screen.getByText('23')).toBeInTheDocument();
    expect(screen.getByText('External Collaborators')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('Elevated Collaborators')).toBeInTheDocument();
  });

  it('renders the tab bar with 5 tabs', () => {
    renderPage();
    const tablist = screen.getByRole('tablist');
    const tabs = within(tablist).getAllByRole('tab');
    expect(tabs).toHaveLength(5);
  });

  it('shows Repository Health pane by default', async () => {
    renderPage();
    const repoTab = screen.getByRole('tab', { name: /Repository Health/ });
    expect(repoTab).toHaveAttribute('aria-selected', 'true');
    expect(
      await screen.findByText(/Branch protection, secret scanning, Dependabot/),
    ).toBeInTheDocument();
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
    expect(screen.getByText(/Stale PRs/i)).toBeInTheDocument();
  });

  it('switches to WAF Insights tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /WAF Insights/ }));
    const wafTab = screen.getByRole('tab', { name: /WAF Insights/ });
    expect(wafTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText(/WAF alignment signals/i)).toBeInTheDocument();
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
});
