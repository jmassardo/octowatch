import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TeamsPane } from './TeamsPane';

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotTeams: vi.fn().mockResolvedValue({
    teams: [
      {
        team_slug: 'frontend',
        team_name: 'Frontend',
        org: 'acme',
        total_members: 12,
        active_users: 10,
        inactive_users: 2,
        adoption_pct: 83,
        avg_days_since_activity: 2,
        at_risk: false,
      },
      {
        team_slug: 'backend',
        team_name: 'Backend',
        org: 'acme',
        total_members: 8,
        active_users: 3,
        inactive_users: 5,
        adoption_pct: 37,
        avg_days_since_activity: 18,
        at_risk: true,
      },
    ],
    total_teams: 2,
    at_risk_count: 1,
  }),
}));

function renderPane() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <TeamsPane />
    </QueryClientProvider>,
  );
}

describe('TeamsPane', () => {
  it('renders team data table', async () => {
    renderPane();
    expect(await screen.findByText('Frontend')).toBeInTheDocument();
    expect(screen.getByText('Backend')).toBeInTheDocument();
  });

  it('shows total teams count', async () => {
    renderPane();
    expect(await screen.findByText('Total Teams')).toBeInTheDocument();
    expect(screen.getByText('At-Risk Teams')).toBeInTheDocument();
  });

  it('shows at-risk count', async () => {
    renderPane();
    expect(await screen.findByText('At-Risk Teams')).toBeInTheDocument();
  });

  it('shows at risk badge for at-risk teams', async () => {
    renderPane();
    expect(await screen.findByText('At Risk')).toBeInTheDocument();
    expect(screen.getByText('Healthy')).toBeInTheDocument();
  });

  it('shows adoption percentages', async () => {
    renderPane();
    expect(await screen.findByText('83%')).toBeInTheDocument();
    expect(screen.getByText('37%')).toBeInTheDocument();
  });
});
