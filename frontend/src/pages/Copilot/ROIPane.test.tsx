import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ROIPane } from './ROIPane';

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotROI: vi.fn().mockResolvedValue({
    summary: {
      total_seats: 100,
      active_seats: 75,
      inactive_seats: 25,
      utilization_pct: 75.0,
      total_monthly_cost: 1900,
      wasted_monthly: 475,
      annual_waste: 5700,
      cost_per_active_user: 25.33,
    },
    tier_breakdown: { power: 30, regular: 45, minimal: 15, inactive: 10 },
    plan_breakdown: { business: 80, enterprise: 20 },
    cost_trend: [],
    recommendations: [
      {
        type: 'reclaim',
        title: 'Reclaim inactive seats',
        impact: 'Save $475/mo',
        priority: 'high' as const,
        description: '25 seats have been inactive for 30+ days.',
      },
    ],
  }),
}));

function renderPane() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ROIPane />
    </QueryClientProvider>,
  );
}

describe('ROIPane', () => {
  it('renders cost summary metrics', async () => {
    renderPane();
    expect(await screen.findByText('Total Seats')).toBeInTheDocument();
    expect(screen.getByText('Active Seats')).toBeInTheDocument();
    expect(screen.getByText('Inactive Seats')).toBeInTheDocument();
    // "Monthly Cost" appears in both stat card and cost efficiency section
    expect(screen.getAllByText('Monthly Cost')).toHaveLength(2);
  });

  it('shows total seat counts', async () => {
    renderPane();
    expect(await screen.findByText('100')).toBeInTheDocument();
    expect(screen.getByText('75')).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument();
  });

  it('shows utilization rate', async () => {
    renderPane();
    expect(await screen.findByText('75.0%')).toBeInTheDocument();
  });

  it('shows wasted monthly spend', async () => {
    renderPane();
    expect(await screen.findByText('$475')).toBeInTheDocument();
    expect(screen.getByText(/Monthly wasted spend/)).toBeInTheDocument();
  });

  it('shows annual savings potential', async () => {
    renderPane();
    expect(await screen.findByText('$5,700')).toBeInTheDocument();
    expect(screen.getByText(/Annual savings potential/)).toBeInTheDocument();
  });

  it('shows recommendations', async () => {
    renderPane();
    expect(await screen.findByText('Reclaim inactive seats')).toBeInTheDocument();
    expect(screen.getByText('25 seats have been inactive for 30+ days.')).toBeInTheDocument();
    expect(screen.getByText('Save $475/mo')).toBeInTheDocument();
  });
});

describe('ROIPane with no data', () => {
  it('shows unavailable message when summary is null', async () => {
    // Clear the module cache and re-mock
    vi.resetModules();
    vi.doMock('../../api/copilotMetrics', () => ({
      getCopilotROI: vi.fn().mockResolvedValue({
        summary: null,
        recommendations: [],
      }),
    }));

    const { ROIPane: ROIPaneNoData } = await import('./ROIPane');
    const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query');
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <ROIPaneNoData />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('ROI Data Unavailable')).toBeInTheDocument();
  });
});
