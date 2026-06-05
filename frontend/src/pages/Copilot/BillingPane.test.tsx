import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { BillingPane } from './BillingPane';

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotBillingOverview: vi.fn().mockResolvedValue({
    pool_total: 10000,
    total_consumed: 3500,
    projected_eom: 7000,
    pool_remaining: 6500,
    utilization_pct: 35.0,
    unique_users: 20,
    daily_rate: 116.67,
    period_start: '2025-01-01',
    days_reported: 15,
  }),
  getCopilotUserBudgets: vi.fn().mockResolvedValue({
    users: [
      {
        login: 'alice',
        org_slug: 'acme',
        consumed: 450.0,
        budget: 500.0,
        utilization_pct: 90.0,
        status: 'near',
        is_blocked: false,
      },
      {
        login: 'bob',
        org_slug: 'acme',
        consumed: 200.0,
        budget: 500.0,
        utilization_pct: 40.0,
        status: 'ok',
        is_blocked: false,
      },
    ],
    total_users: 2,
    buckets: { '0-50': 1, '50-80': 0, '80-90': 0, '90-100': 1, '100+': 0 },
  }),
  getCopilotBillingTrends: vi.fn().mockResolvedValue({
    trends: [
      {
        date: '2025-01-14',
        total: 100,
        completions: 60,
        chat: 25,
        pr: 10,
        other: 5,
        active_users: 15,
      },
      {
        date: '2025-01-15',
        total: 120,
        completions: 70,
        chat: 30,
        pr: 12,
        other: 8,
        active_users: 18,
      },
    ],
    period_days: 30,
  }),
}));

function renderBillingPane() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <BillingPane />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('BillingPane', () => {
  it('renders pool overview cards', async () => {
    renderBillingPane();
    await waitFor(() => {
      expect(screen.getByText('AI Credit Pool')).toBeInTheDocument();
    });
    expect(screen.getByText('Consumed This Period')).toBeInTheDocument();
    expect(screen.getByText('Projected End-of-Month')).toBeInTheDocument();
    expect(screen.getByText('Pool Remaining')).toBeInTheDocument();
  });

  it('renders utilization histogram section', async () => {
    renderBillingPane();
    await waitFor(() => {
      expect(screen.getByText('Budget Utilization Distribution')).toBeInTheDocument();
    });
  });

  it('renders spend trend chart section', async () => {
    renderBillingPane();
    await waitFor(() => {
      expect(screen.getByText('Daily Credit Consumption (30 days)')).toBeInTheDocument();
    });
  });

  it('renders user budgets table', async () => {
    renderBillingPane();
    await waitFor(() => {
      expect(screen.getByText('User Budgets')).toBeInTheDocument();
    });
    // Check search input exists
    expect(screen.getByPlaceholderText('Search users...')).toBeInTheDocument();
  });

  it('displays user data in the table', async () => {
    renderBillingPane();
    await waitFor(() => {
      expect(screen.getByText('alice')).toBeInTheDocument();
    });
    expect(screen.getByText('bob')).toBeInTheDocument();
  });

  it('shows status badges for users', async () => {
    renderBillingPane();
    await waitFor(() => {
      expect(screen.getByText('Near Limit')).toBeInTheDocument();
    });
    expect(screen.getByText('OK')).toBeInTheDocument();
  });

  it('displays bucket distribution text', async () => {
    renderBillingPane();
    await waitFor(() => {
      expect(screen.getByText('2 users across all organizations')).toBeInTheDocument();
    });
  });
});
