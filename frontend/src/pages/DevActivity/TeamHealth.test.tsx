import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { TeamHealthPane } from './TeamHealthPane';

// ---------------------------------------------------------------------------
// Mock data (vi.hoisted so available inside vi.mock factories)
// ---------------------------------------------------------------------------

const { mockSummary, mockBusFactor, mockEngagement, mockViolations, mockConcentration } =
  vi.hoisted(() => {
    const mockSummary = {
      bus_factor_score: 2,
      active_contributors_pct: 45.0,
      total_developers: 20,
      dormant_developers: 5,
      policy_violations_count: 3,
      policy_violations_trend: 'up' as const,
      knowledge_concentration_risk: 'medium' as const,
      engagement_counts: { active: 9, regular: 4, occasional: 2, dormant: 5 },
    };

    const mockBusFactor = {
      repos: [
        {
          repo: 'org/critical-repo',
          bus_factor: 1,
          contributor_count: 1,
          top_contributors: [{ login: 'alice', pct: 100 }],
          risk_level: 'critical' as const,
        },
        {
          repo: 'org/healthy-repo',
          bus_factor: 4,
          contributor_count: 6,
          top_contributors: [
            { login: 'bob', pct: 25 },
            { login: 'carol', pct: 22 },
            { login: 'dave', pct: 20 },
            { login: 'eve', pct: 18 },
          ],
          risk_level: 'low' as const,
        },
      ],
      lookback_days: 90,
    };

    const mockEngagement = {
      tiers: {
        active: [{ login: 'alice', last_active: new Date().toISOString(), event_count: 50 }],
        regular: [
          {
            login: 'bob',
            last_active: new Date(Date.now() - 10 * 86_400_000).toISOString(),
            event_count: 20,
          },
        ],
        occasional: [
          {
            login: 'carol',
            last_active: new Date(Date.now() - 20 * 86_400_000).toISOString(),
            event_count: 5,
          },
        ],
        dormant: [
          {
            login: 'dormant-dave',
            last_active: new Date(Date.now() - 45 * 86_400_000).toISOString(),
            event_count: 2,
          },
        ],
      },
      counts: { active: 1, regular: 1, occasional: 1, dormant: 1 },
      total_developers: 4,
      active_pct: 25.0,
      trend: [
        { month: '2026-01-01', active_developers: 3 },
        { month: '2026-02-01', active_developers: 4 },
        { month: '2026-03-01', active_developers: 2 },
      ],
      lookback_days: 30,
    };

    const mockViolations = {
      violations: [
        {
          type: 'branch_protection_bypass',
          severity: 'high' as const,
          description: 'Branch protection policy override',
          actor: 'alice',
          repo: 'org/repo-a',
          org: 'org',
          timestamp: new Date().toISOString(),
          action: 'protected_branch.policy_override',
        },
        {
          type: 'force_push_default_branch',
          severity: 'high' as const,
          description: 'Force push to default branch',
          actor: 'bob',
          repo: 'org/repo-b',
          org: 'org',
          timestamp: new Date().toISOString(),
          action: 'git.push',
        },
        {
          type: '2fa_disabled',
          severity: 'critical' as const,
          description: 'Two-factor authentication disabled',
          actor: 'carol',
          repo: null,
          org: 'org',
          timestamp: new Date().toISOString(),
          action: 'two_factor_authentication.disabled',
        },
      ],
      current_count: 3,
      previous_count: 1,
      trend_direction: 'up' as const,
      lookback_days: 30,
    };

    const mockConcentration = {
      risks: [
        {
          repo: 'org/critical-repo',
          top_actor: 'alice',
          concentration_pct: 85.0,
          total_events: 100,
          risk_level: 'high' as const,
          recommendation:
            'Consider cross-team code reviews for org/critical-repo to reduce dependency on @alice',
        },
      ],
      lookback_days: 90,
    };

    return { mockSummary, mockBusFactor, mockEngagement, mockViolations, mockConcentration };
  });

// ---------------------------------------------------------------------------
// Mock API modules
// ---------------------------------------------------------------------------

vi.mock('../../api/teamHealth', () => ({
  getTeamHealthSummary: vi.fn().mockImplementation(() => Promise.resolve(mockSummary)),
  getBusFactorAnalysis: vi.fn().mockImplementation(() => Promise.resolve(mockBusFactor)),
  getEngagement: vi.fn().mockImplementation(() => Promise.resolve(mockEngagement)),
  getPolicyViolations: vi.fn().mockImplementation(() => Promise.resolve(mockViolations)),
  getKnowledgeConcentration: vi.fn().mockImplementation(() => Promise.resolve(mockConcentration)),
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('TeamHealthPane', () => {
  it('renders all MetricCard indicators', async () => {
    renderWithProviders(<TeamHealthPane />);

    expect(await screen.findByText('Bus Factor Score')).toBeInTheDocument();
    expect(screen.getByText('Active Contributors')).toBeInTheDocument();
    expect(screen.getByText('Dormant Developers')).toBeInTheDocument();
    expect(screen.getByText('Policy Violations (30d)')).toBeInTheDocument();
    expect(screen.getByText('Knowledge Concentration')).toBeInTheDocument();
  });

  it('renders bus factor score value from summary', async () => {
    renderWithProviders(<TeamHealthPane />);

    // Bus factor score = 2 from mock — find within the MetricCard context
    const busFactorCard = await screen.findByText('Bus Factor Score');
    expect(busFactorCard).toBeInTheDocument();
    // The value "2" is rendered in the same MetricCard parent
    const cardParent = busFactorCard.closest('[class*="metric"]');
    expect(cardParent).not.toBeNull();
    expect(cardParent!.textContent).toContain('2');
  });

  it('renders the Bus Factor Risk section', async () => {
    renderWithProviders(<TeamHealthPane />);

    expect(await screen.findByText('Bus Factor Risk')).toBeInTheDocument();
    expect(screen.getByText('Per-repo bus factor')).toBeInTheDocument();
  });

  it('renders bus factor repo data in the table', async () => {
    renderWithProviders(<TeamHealthPane />);

    // Both repos appear (may appear multiple times due to concentration section)
    const criticalRepos = await screen.findAllByText('org/critical-repo');
    expect(criticalRepos.length).toBeGreaterThanOrEqual(1);
    const healthyRepos = screen.getAllByText('org/healthy-repo');
    expect(healthyRepos.length).toBeGreaterThanOrEqual(1);
  });

  it('renders risk badges with correct text', async () => {
    renderWithProviders(<TeamHealthPane />);

    await screen.findAllByText('org/critical-repo');
    const badges = screen.getAllByText('critical');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it('renders the Developer Engagement section with stacked bar', async () => {
    renderWithProviders(<TeamHealthPane />);

    expect(await screen.findByText('Developer Engagement')).toBeInTheDocument();
    expect(screen.getByText('Engagement distribution')).toBeInTheDocument();

    // Should show legend items
    expect(screen.getByText(/Active \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Regular \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Occasional \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Dormant \(1\)/)).toBeInTheDocument();
  });

  it('renders the engagement trend chart', async () => {
    renderWithProviders(<TeamHealthPane />);

    expect(
      await screen.findByText('Monthly active developers (last 3 months)'),
    ).toBeInTheDocument();
    expect(screen.getByText('2026-01')).toBeInTheDocument();
    expect(screen.getByText('2026-02')).toBeInTheDocument();
    expect(screen.getByText('2026-03')).toBeInTheDocument();
  });

  it('renders dormant developers table', async () => {
    renderWithProviders(<TeamHealthPane />);

    // CardHeader for dormant
    expect(await screen.findByText(/Dormant developers/)).toBeInTheDocument();
    expect(screen.getByText('@dormant-dave')).toBeInTheDocument();
  });

  it('renders Policy Violations section', async () => {
    renderWithProviders(<TeamHealthPane />);

    expect(await screen.findByText('Policy Violations')).toBeInTheDocument();
    expect(screen.getByText('Branch protection policy override')).toBeInTheDocument();
    expect(screen.getByText('Force push to default branch')).toBeInTheDocument();
    expect(screen.getByText('Two-factor authentication disabled')).toBeInTheDocument();
  });

  it('filters violations by type when filter button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<TeamHealthPane />);

    await screen.findByText('Branch protection policy override');

    // Click the "2FA disabled" filter
    await user.click(screen.getByText('2FA disabled'));

    // Should show only the 2FA violation
    expect(screen.getByText('Two-factor authentication disabled')).toBeInTheDocument();
    expect(screen.queryByText('Branch protection policy override')).not.toBeInTheDocument();
  });

  it('renders Knowledge Concentration Risks section', async () => {
    renderWithProviders(<TeamHealthPane />);

    expect(await screen.findByText('Knowledge Concentration Risks')).toBeInTheDocument();
    expect(screen.getByText('High-concentration repos')).toBeInTheDocument();
  });

  it('shows recommendation for concentrated repos', async () => {
    renderWithProviders(<TeamHealthPane />);

    expect(
      await screen.findByText(/Consider cross-team code reviews for org\/critical-repo/),
    ).toBeInTheDocument();
  });

  it('renders violation filter buttons', async () => {
    renderWithProviders(<TeamHealthPane />);

    await screen.findByText('All types');
    expect(screen.getByText('Branch protection')).toBeInTheDocument();
    expect(screen.getByText('Force push')).toBeInTheDocument();
    expect(screen.getByText('Permission escalation')).toBeInTheDocument();
    expect(screen.getByText('SSH key added')).toBeInTheDocument();
  });

  it('shows active contributors percentage', async () => {
    renderWithProviders(<TeamHealthPane />);

    // 45% from mock summary
    expect(await screen.findByText('45%')).toBeInTheDocument();
  });

  it('shows dormant developer count', async () => {
    renderWithProviders(<TeamHealthPane />);

    // dormant_developers = 5 from mock summary — find within MetricCard context
    const dormantCard = await screen.findByText('Dormant Developers');
    const cardParent = dormantCard.closest('[class*="metric"]');
    expect(cardParent).not.toBeNull();
    expect(cardParent!.textContent).toContain('5');
  });

  it('shows policy violations trend direction', async () => {
    renderWithProviders(<TeamHealthPane />);

    // trend_direction = 'up', rendered as delta
    expect(await screen.findByText('↑ vs prev 30d')).toBeInTheDocument();
  });

  it('shows knowledge concentration risk level', async () => {
    renderWithProviders(<TeamHealthPane />);

    // knowledge_concentration_risk = 'medium', rendered capitalized
    expect(await screen.findByText('Medium')).toBeInTheDocument();
  });
});
