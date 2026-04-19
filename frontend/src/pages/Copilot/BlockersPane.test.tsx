import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BlockersPane } from './BlockersPane';

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotBlockers: vi.fn().mockResolvedValue({
    blockers: [
      {
        id: 'no-seat-1',
        category: 'no_seat',
        title: 'Developers without Copilot seats',
        description: '5 developers have no seat assigned.',
        severity: 'high',
        count: 5,
        affected_users: ['alice', 'bob', 'carol', 'dave', 'eve'],
        recommendation: 'Assign seats to these developers.',
      },
      {
        id: 'inactive-1',
        category: 'inactive_seat',
        title: 'Inactive seat holders',
        description: '3 users have not used Copilot in 30+ days.',
        severity: 'medium',
        count: 3,
        affected_users: ['frank', 'grace', 'heidi'],
        recommendation: 'Consider revoking or reassigning these seats.',
      },
    ],
    quick_wins: [
      { action: 'Assign 5 pending seats', description: 'Quick onboarding', impact: '+5 users' },
    ],
    summary: {
      total_blockers: 8,
      no_seat_count: 5,
      inactive_count: 3,
      policy_restricted_count: 0,
    },
  }),
}));

function renderPane() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <BlockersPane />
    </QueryClientProvider>,
  );
}

describe('BlockersPane', () => {
  it('renders blocker summary metrics', async () => {
    renderPane();
    expect(await screen.findByText('8')).toBeInTheDocument();
    expect(screen.getByText('Total Blockers')).toBeInTheDocument();
    expect(screen.getByText('Without Seats')).toBeInTheDocument();
    expect(screen.getByText('Inactive Seats')).toBeInTheDocument();
  });

  it('shows quick wins section', async () => {
    renderPane();
    expect(await screen.findByText('Quick Wins')).toBeInTheDocument();
    expect(screen.getByText('Assign 5 pending seats')).toBeInTheDocument();
    expect(screen.getByText('+5 users')).toBeInTheDocument();
  });

  it('shows blocker details', async () => {
    renderPane();
    expect(await screen.findByText('Developers without Copilot seats')).toBeInTheDocument();
    expect(screen.getByText('Inactive seat holders')).toBeInTheDocument();
  });

  it('shows recommendations for blockers', async () => {
    renderPane();
    expect(await screen.findByText(/Assign seats to these developers/)).toBeInTheDocument();
  });

  it('shows export CSV button', async () => {
    renderPane();
    expect(await screen.findByText('Export CSV')).toBeInTheDocument();
  });
});
