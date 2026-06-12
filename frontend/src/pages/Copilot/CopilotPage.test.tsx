import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { CopilotPage } from './index';
import { useFeatures } from '../../hooks/useFeatures';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

vi.mock('../../api/reports', () => ({
  getSeatUtilizationReport: vi.fn().mockResolvedValue({
    data: [
      {
        bucket: '2024-01-15',
        active_seat_count: 124,
        provisioned_seat_count: 186,
        utilization_pct: 66.7,
      },
    ],
  }),
}));

vi.mock('../../api/features', () => ({
  getFeatures: vi.fn().mockResolvedValue({
    copilot_insights: true,
    velocity: true,
    dev_activity: true,
    org_health: true,
  }),
  updateFeatures: vi.fn().mockResolvedValue({}),
}));

vi.mock('../../hooks/useFeatures', () => ({
  useFeatures: vi.fn().mockReturnValue({
    features: {
      copilot_insights: true,
      velocity: true,
      dev_activity: true,
      org_health: true,
    },
    isLoading: false,
    toggleFeature: vi.fn(),
    isToggling: false,
  }),
}));

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotOverview: vi.fn().mockResolvedValue({
    acceptance_rate_days: [
      '2026-06-01',
      '2026-06-02',
      '2026-06-03',
      '2026-06-04',
      '2026-06-05',
      '2026-06-06',
      '2026-06-07',
    ],
    acceptance_rate_values: [24, 26, 27, 25, 28, 31, 29],
    acceptance_threshold: 25,
    languages: [
      { lang: 'TypeScript', pct: 38, color: '#3fb950' },
      { lang: 'Python', pct: 34, color: '#3fb950' },
    ],
    total_active_users: 120,
    total_engaged_users: 98,
    total_provisioned_seats: 186,
  }),
  getCopilotAnomalies: vi.fn().mockResolvedValue({
    anomalies: [
      {
        id: 1,
        severity: 'high',
        title: 'Sudden drop in acceptance rate',
        description: 'Acceptance rate dropped 15% in Backend team.',
        timestamp: '2 hours ago',
        team: 'Backend',
      },
      {
        id: 2,
        severity: 'medium',
        title: 'Unusual seat churn detected',
        description: '12 seats were revoked.',
        timestamp: '6 hours ago',
        team: 'Platform',
      },
      {
        id: 3,
        severity: 'low',
        title: 'Knowledge base usage spike',
        description: 'Knowledge base queries increased 340%.',
        timestamp: '1 day ago',
        team: 'ML/AI',
      },
    ],
  }),
  getCopilotAdoption: vi.fn().mockResolvedValue({
    tiers: [
      { id: 'power', label: 'Power Users', count: 34, color: '#3fb950', desc: 'Active every day' },
      { id: 'regular', label: 'Regular', count: 68, color: '#58a6ff', desc: '3-4 days/week' },
      { id: 'minimal', label: 'Minimal', count: 22, color: '#d29922', desc: '1-2 uses in 30d' },
      { id: 'inactive', label: 'Inactive', count: 38, color: '#f85149', desc: 'Cold 30d+' },
      { id: 'never', label: 'Never Used', count: 24, color: '#8b949e', desc: 'Zero activity' },
    ],
    total_adoption: 186,
    power_users: [{ user: 'sarah.chen', days_active: 45, features_used: 5 }],
    feature_adoption: [{ feature: 'IDE completions', pct: 87, color: '#3fb950' }],
    minimal_users: [],
  }),
  getCopilotModels: vi.fn().mockResolvedValue({
    models: [{ model: 'GPT-4o', pct: 42, color: '#58a6ff' }],
    features: [{ feature: 'IDE completions', count: 142, color: '#58a6ff' }],
    editors: [{ name: 'VS Code', count: 112, pct: 79 }],
  }),
  getCopilotModelUsers: vi.fn().mockResolvedValue({
    users: [],
    total_users: 0,
  }),
  getCopilotBlockers: vi.fn().mockResolvedValue({
    blockers: [],
    quick_wins: [],
    summary: { total_blockers: 0, no_seat_count: 0, inactive_count: 0, policy_restricted_count: 0 },
  }),
  getCopilotTeams: vi.fn().mockResolvedValue({ teams: [], total_teams: 0, at_risk_count: 0 }),
  getCopilotPolicyChanges: vi.fn().mockResolvedValue({ timeline: [], total_changes: 0 }),
  getCopilotROI: vi.fn().mockResolvedValue({ summary: null, recommendations: [] }),
  getCopilotActivity: vi.fn().mockResolvedValue({
    dates: [],
    ide_dau: [],
    ide_wau: [],
    completions_count: [],
    completions_accepted: [],
    acceptance_rate_pct: [],
    chat_requests_per_user: [],
    requests_per_mode: { dates: [], completions: [], chat: [], dotcom_chat: [], pr: [] },
  }),
  getCopilotChatMetrics: vi.fn().mockResolvedValue({
    dates: [],
    total_interactions: [],
    code_actions: [],
    active_chat_users: [],
    action_rate_pct: [],
  }),
  getCopilotLanguageBreakdown: vi.fn().mockResolvedValue({
    dates: [],
    language_per_day: {},
    language_distribution: [],
    model_per_language: { labels: [], series: [] },
    acceptance_by_editor: [],
    top_by_generations: [],
    top_by_lines: [],
  }),
  getCopilotPRMetrics: vi.fn().mockResolvedValue({
    dates: [],
    pr_activity: [],
    pr_contributions: [],
    review_suggestions: [],
  }),
  getCopilotAgentActivity: vi.fn().mockResolvedValue({
    dates: [],
    daily_lines_added: [],
    daily_lines_accepted: [],
    lines_by_mode: {},
    lines_by_model: [],
    lines_by_language: [],
  }),
}));

vi.mock('../../api/copilotGovernance', () => ({
  listCopilotPolicies: vi.fn().mockResolvedValue([]),
  listCopilotViolations: vi.fn().mockResolvedValue({ violations: [], total: 0 }),
  updateCopilotPolicy: vi.fn().mockResolvedValue({}),
}));

function renderPage(initialTab = 'overview') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter
        initialEntries={[`/copilot/${initialTab}`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <Routes>
          <Route path="/copilot/:tab" element={<CopilotPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CopilotPage', () => {
  it('renders page title and subtitle', () => {
    renderPage();
    expect(screen.getByText('Copilot Insights')).toBeInTheDocument();
    expect(
      screen.getByText('GitHub Copilot usage analytics and adoption metrics'),
    ).toBeInTheDocument();
  });

  it('renders the tab bar with 16 tabs', () => {
    renderPage();
    const tablist = screen.getByRole('tablist');
    const tabs = within(tablist).getAllByRole('tab');
    expect(tabs).toHaveLength(16);
  });

  it('shows the anomaly badge with count 3', async () => {
    renderPage();
    const tablist = screen.getByRole('tablist');
    const anomaliesTab = within(tablist).getByRole('tab', { name: /Anomalies/ });
    // Wait for the anomaly data to load and badge to update
    await screen.findByText(/Seat waste detected/);
    // The badge count may take a moment to appear from async query
    expect(anomaliesTab).toHaveTextContent(/3/);
  });

  it('shows overview content by default', async () => {
    renderPage();
    expect(await screen.findByText(/Seat waste detected/)).toBeInTheDocument();
    expect(screen.getByText('Export inactive list')).toBeInTheDocument();
  });

  it('switches to the adoption tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Adoption/ }));
    expect(await screen.findByText('Adoption tiers')).toBeInTheDocument();
    expect(await screen.findByText('Power Users')).toBeInTheDocument();
    expect(screen.getByText('Copilot users')).toBeInTheDocument();
    expect(screen.queryByText(/Seat waste detected/)).not.toBeInTheDocument();
  });

  it('switches to the models tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Models/ }));
    expect(await screen.findByText('Model usage distribution')).toBeInTheDocument();
    expect(screen.getByText('Feature usage distribution')).toBeInTheDocument();
    expect(screen.getByText('Editor breakdown')).toBeInTheDocument();
    expect(screen.queryByText(/Seat waste detected/)).not.toBeInTheDocument();
  });

  it('switches to the license tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /License/ }));
    expect(screen.getByText('Cost optimization summary')).toBeInTheDocument();
    expect(screen.getByText('Recommendations')).toBeInTheDocument();
    expect(screen.getByText(/Consider just-in-time provisioning/)).toBeInTheDocument();
    expect(screen.queryByText(/Seat waste detected/)).not.toBeInTheDocument();
  });

  it('switches to the anomalies tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Anomalies/ }));
    expect(await screen.findByText('Sudden drop in acceptance rate')).toBeInTheDocument();
    expect(screen.getByText('Unusual seat churn detected')).toBeInTheDocument();
    expect(screen.getByText('Knowledge base usage spike')).toBeInTheDocument();
    expect(
      screen.getByText((_content, element) => {
        return (
          element?.classList?.contains('insightNote') === true &&
          element.textContent?.includes('3 anomalies') === true
        );
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Seat waste detected/)).not.toBeInTheDocument();
  });

  it('can switch back to overview after navigating to another tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('tab', { name: /Adoption/ }));
    expect(await screen.findByText('Adoption tiers')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /Overview/ }));
    expect(await screen.findByText(/Seat waste detected/)).toBeInTheDocument();
    expect(screen.queryByText('Adoption tiers')).not.toBeInTheDocument();
  });

  it('shows disabled message when copilot_insights feature is off', () => {
    vi.mocked(useFeatures).mockReturnValue({
      features: {
        copilot_insights: false,
        velocity: true,
        dev_activity: true,
        org_health: true,
      },
      isLoading: false,
      toggleFeature: vi.fn(),
      isToggling: false,
    });

    renderPage();

    expect(screen.getByText('Copilot Insights is disabled')).toBeInTheDocument();
    expect(screen.getByText(/Settings → Features/)).toBeInTheDocument();

    // Restore mock for other tests
    vi.mocked(useFeatures).mockReturnValue({
      features: {
        copilot_insights: true,
        velocity: true,
        dev_activity: true,
        org_health: true,
      },
      isLoading: false,
      toggleFeature: vi.fn(),
      isToggling: false,
    });
  });
});
