import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { LicensePane } from './LicensePane';
import type { SeatUtilizationBucket } from '../../types/reports';

vi.mock('../../hooks/useOrgConfig', () => ({
  useOrgConfig: () => ({
    costPerSeat: 19,
    isLoading: false,
    isError: false,
    orgConfig: undefined,
  }),
}));

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotROI: vi.fn().mockResolvedValue({
    ghost_members: [
      { user: 'ghost-alice', last_activity: '2024-09-01T00:00:00Z', days_inactive: 120 },
      { user: 'ghost-bob', last_activity: 'Never', days_inactive: 999 },
    ],
    license_optimization: {
      ghost_member_count: 2,
      inactive_savings_monthly: 38,
      inactive_savings_annual: 456,
    },
    growth_forecast: {
      current_active: 50,
      projected_30d: 55,
      projected_90d: 65,
      monthly_growth_pct: 10,
      weeks_to_capacity: 12,
    },
  }),
}));

const sampleBuckets: SeatUtilizationBucket[] = [
  {
    bucket: '2025-01-01',
    provisioned_seat_count: 100,
    active_seat_count: 70,
    utilization_pct: 70,
  },
  {
    bucket: '2025-01-02',
    provisioned_seat_count: 100,
    active_seat_count: 75,
    utilization_pct: 75,
  },
];

function renderPane(buckets: SeatUtilizationBucket[] = sampleBuckets) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={queryClient}>
        <LicensePane seatBuckets={buckets} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('LicensePane', () => {
  it('renders summary metric cards', async () => {
    renderPane();
    expect(await screen.findByText('Total seats')).toBeInTheDocument();
    expect(screen.getByText('Active seats')).toBeInTheDocument();
    expect(screen.getByText('Inactive seats')).toBeInTheDocument();
    expect(screen.getByText('Monthly waste')).toBeInTheDocument();
  });

  it('shows correct seat counts from latest bucket', async () => {
    renderPane();
    // Latest bucket: 100 total, 75 active, 25 inactive
    expect(await screen.findByText('100')).toBeInTheDocument();
    expect(screen.getByText('75')).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument();
  });

  it('shows cost optimization summary', async () => {
    renderPane();
    expect(await screen.findByText('Cost optimization summary')).toBeInTheDocument();
    expect(screen.getByText('Current monthly spend')).toBeInTheDocument();
    expect(screen.getByText('Potential monthly savings')).toBeInTheDocument();
  });

  it('shows recommendations section', async () => {
    renderPane();
    expect(await screen.findByText('Recommendations')).toBeInTheDocument();
    expect(screen.getByText('Consider just-in-time provisioning')).toBeInTheDocument();
  });

  it('opens drill-down modal when clicking Total seats', async () => {
    const user = userEvent.setup();
    renderPane();
    const totalCard = (await screen.findByText('Total seats')).closest('[role="button"]')!;
    await user.click(totalCard);
    expect(screen.getByText('Total seats — provisioned over time')).toBeInTheDocument();
  });

  it('shows empty state when no buckets provided', async () => {
    renderPane([]);
    expect(await screen.findByText(/No Copilot seat data available/)).toBeInTheDocument();
    expect(screen.getByText('Integrations page')).toBeInTheDocument();
  });
});

describe('LicensePane ghost members', () => {
  it('renders ghost members table', async () => {
    renderPane();
    expect(await screen.findByText('Ghost Members')).toBeInTheDocument();
    expect(screen.getByText(/2 users with 60\+ days of inactivity/)).toBeInTheDocument();
  });

  it('shows ghost member usernames', async () => {
    renderPane();
    expect(await screen.findByText('ghost-alice')).toBeInTheDocument();
    expect(screen.getByText('ghost-bob')).toBeInTheDocument();
  });

  it('shows suggested action for ghost members', async () => {
    renderPane();
    await screen.findByText('ghost-alice');
    const revokeElements = screen.getAllByText('Revoke');
    expect(revokeElements.length).toBe(2);
  });
});

describe('LicensePane savings opportunity', () => {
  it('shows monthly and annual savings cards', async () => {
    renderPane();
    expect(await screen.findByText('Monthly Savings')).toBeInTheDocument();
    expect(screen.getByText('Annual Savings')).toBeInTheDocument();
  });

  it('shows ghost seat reclaim delta', async () => {
    renderPane();
    expect(await screen.findByText(/Reclaim 2 ghost seats/)).toBeInTheDocument();
  });
});

describe('LicensePane growth forecast', () => {
  it('renders growth forecast card', async () => {
    renderPane();
    expect(await screen.findByText('Growth Forecast')).toBeInTheDocument();
  });

  it('shows current active and projections', async () => {
    renderPane();
    expect(await screen.findByText('Current Active')).toBeInTheDocument();
    expect(screen.getByText('30-Day Projection')).toBeInTheDocument();
    expect(screen.getByText('90-Day Projection')).toBeInTheDocument();
    expect(screen.getByText('Monthly Growth')).toBeInTheDocument();
  });

  it('shows projection values', async () => {
    renderPane();
    expect(await screen.findByText('50')).toBeInTheDocument();
    expect(screen.getByText('55')).toBeInTheDocument();
    expect(screen.getByText('65')).toBeInTheDocument();
  });

  it('shows weeks-to-capacity warning', async () => {
    renderPane();
    expect(
      await screen.findByText(/you will reach seat capacity in approximately/),
    ).toBeInTheDocument();
    expect(screen.getByText('12 weeks')).toBeInTheDocument();
  });
});
