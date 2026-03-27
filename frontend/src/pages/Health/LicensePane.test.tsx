import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { LicensePane } from './LicensePane';
import { GHOST_MEMBERS, LICENSE_SAMPLE, COPILOT_CROSS_REF } from './healthData';

vi.mock('../../api/reports', () => ({
  getSeatUtilizationReport: vi.fn().mockResolvedValue({ data: [] }),
  getCopilotSeatsReport: vi.fn().mockResolvedValue({ data: [] }),
}));

function renderWithProviders() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LicensePane />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LicensePane', () => {
  it('renders the sample data banner', () => {
    renderWithProviders();
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText(/sample values/)).toBeInTheDocument();
  });

  it('renders total seats card with utilization gauge', () => {
    renderWithProviders();
    expect(screen.getByText('Total seats (GitHub)')).toBeInTheDocument();
    expect(screen.getByText(`/ ${LICENSE_SAMPLE.seatLimit}`)).toBeInTheDocument();
    expect(screen.getByText(`${LICENSE_SAMPLE.utilizationPct}% utilized`, { exact: false })).toBeInTheDocument();
  });

  it('renders ghost members card with count and cost', () => {
    renderWithProviders();
    // "Ghost members" appears multiple times (card title + section title + metric card)
    const ghostTexts = screen.getAllByText('Ghost members');
    expect(ghostTexts.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(`≈ $${LICENSE_SAMPLE.ghostMonthlyCost}/month recoverable`)).toBeInTheDocument();
    expect(screen.getByText('Dormant 90d+ still consuming a seat')).toBeInTheDocument();
  });

  it('renders growth forecast card', () => {
    renderWithProviders();
    expect(screen.getByText('Growth forecast')).toBeInTheDocument();
    // ~74d appears in both the card and the metric card
    const forecastTexts = screen.getAllByText(`~${LICENSE_SAMPLE.growthForecastDays}d`);
    expect(forecastTexts.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(`+${LICENSE_SAMPLE.growthRate}/month rate`, { exact: false })).toBeInTheDocument();
  });

  it('renders ghost members table with all sample members', () => {
    renderWithProviders();
    expect(screen.getByText('Ghost members — consuming seats with no activity')).toBeInTheDocument();

    for (const member of GHOST_MEMBERS) {
      expect(screen.getByText(member.member)).toBeInTheDocument();
    }
  });

  it('renders ghost member status labels', () => {
    renderWithProviders();
    const dormantLabels = screen.getAllByText('dormant');
    expect(dormantLabels.length).toBe(3);
    expect(screen.getByText('stale & dormant')).toBeInTheDocument();
  });

  it('renders ghost member details correctly', () => {
    renderWithProviders();
    // Check first member
    expect(screen.getByText('legacy-bot-1')).toBeInTheDocument();
    expect(screen.getByText('102')).toBeInTheDocument();
  });

  it('renders copilot seat cross-reference', () => {
    renderWithProviders();
    expect(screen.getByText('Copilot seat waste for reference')).toBeInTheDocument();
    expect(
      screen.getByText(`${COPILOT_CROSS_REF.inactiveSeats} of ${COPILOT_CROSS_REF.totalSeats} Copilot seats`),
    ).toBeInTheDocument();
  });

  it('renders data source note', () => {
    renderWithProviders();
    expect(screen.getByText(/License seat data is derived from/)).toBeInTheDocument();
  });

  it('renders summary MetricCards', () => {
    renderWithProviders();
    expect(screen.getByText('Seat utilization')).toBeInTheDocument();
    expect(screen.getByText('Days to limit')).toBeInTheDocument();
    expect(screen.getByText('Copilot waste')).toBeInTheDocument();
  });

  it('renders the table header columns', () => {
    renderWithProviders();
    const table = screen.getByText('Member').closest('table')!;
    const headers = within(table).getAllByRole('columnheader');
    const headerTexts = headers.map((h) => h.textContent);
    expect(headerTexts).toEqual([
      'Member',
      'Org',
      'Role',
      'Last seen',
      'Days inactive',
      'Licenses held',
      'Status',
    ]);
  });

  it('renders ghost member org info', () => {
    renderWithProviders();
    const acmeCells = screen.getAllByText('acme-corp');
    expect(acmeCells.length).toBe(3);
    expect(screen.getByText('globex')).toBeInTheDocument();
  });
});
