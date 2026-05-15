import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { LicensePane } from './LicensePane';

const COST_PER_SEAT_DEFAULT = 19;

vi.mock('../../hooks/useOrgConfig', () => ({
  useOrgConfig: () => ({
    costPerSeat: COST_PER_SEAT_DEFAULT,
    isLoading: false,
    isError: false,
    orgConfig: undefined,
  }),
}));

vi.mock('../../hooks/useOrg', () => ({
  useOrg: () => ({ selectedOrg: '', setSelectedOrg: vi.fn() }),
}));

vi.mock('../../api/reports', () => ({
  getSeatUtilizationReport: vi.fn(),
  getCopilotSeatsReport: vi.fn(),
}));

vi.mock('../../api/healthSignals', () => ({
  getGhostMembers: vi.fn(),
  getLicenseConsumption: vi.fn(),
}));

const mockSeatData = {
  data: [{ provisioned_seat_count: 100, active_seat_count: 82, utilization_pct: 82 }],
};

const mockCopilotData = {
  data: [{ seats_net: 45 }],
};

const mockGhostMembers = {
  ghost_members: [
    { actor: 'legacy-bot-1', last_active: '2024-12-01T00:00:00Z' },
    { actor: 'old-dev-2', last_active: null },
  ],
};

// Track which useQuery call index we're on per render
let useQueryCallIndex: number;

const mockQueryReturns: Array<{
  data: unknown;
  isLoading: boolean;
  isError: boolean;
  refetch: ReturnType<typeof vi.fn>;
}> = [];

vi.mock('@tanstack/react-query', async () => {
  const actual =
    await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQuery: () => {
      const idx = useQueryCallIndex++;
      return (
        mockQueryReturns[idx] || {
          data: undefined,
          isLoading: false,
          isError: false,
          refetch: vi.fn(),
        }
      );
    },
  };
});

function renderWithProviders() {
  useQueryCallIndex = 0;
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <LicensePane />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const mockLicenseConsumption = {
  enterprise_slug: 'test-enterprise',
  total_seats_purchased: 200,
  total_seats_consumed: 150,
  seats_available: 50,
  utilization_pct: 75,
  synced_at: '2024-03-28T10:00:00Z',
};

function setDefaultData() {
  mockQueryReturns.length = 0;
  // Call 0: license consumption (first query in the component)
  mockQueryReturns.push({
    data: mockLicenseConsumption,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  });
  // Call 1: seat utilization
  mockQueryReturns.push({ data: mockSeatData, isLoading: false, isError: false, refetch: vi.fn() });
  // Call 2: copilot seats
  mockQueryReturns.push({
    data: mockCopilotData,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  });
  // Call 3: ghost members
  mockQueryReturns.push({
    data: mockGhostMembers,
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  });
}

describe('LicensePane', () => {
  beforeEach(() => {
    setDefaultData();
  });

  it('renders total seats card', () => {
    renderWithProviders();
    expect(screen.getByText('Total seats (GitHub)')).toBeInTheDocument();
    // With GHEC license data, shows consumed/purchased from enterprise sync
    expect(screen.getByText('/ 200')).toBeInTheDocument();
    expect(screen.getByText(/75% utilized/)).toBeInTheDocument();
  });

  it('renders ghost members card with count', () => {
    renderWithProviders();
    const ghostTexts = screen.getAllByText('Ghost members');
    expect(ghostTexts.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Dormant 90d+ still consuming a seat')).toBeInTheDocument();
    const expectedCost = 2 * COST_PER_SEAT_DEFAULT;
    expect(screen.getByText(`≈ $${expectedCost}/month recoverable`)).toBeInTheDocument();
  });

  it('renders Available seats card when license sync data is present', () => {
    renderWithProviders();
    const activeLabels = screen.getAllByText('Available seats');
    expect(activeLabels.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Seats remaining within your license')).toBeInTheDocument();
  });

  it('renders ghost member table with 2 columns (Member, Last active)', () => {
    renderWithProviders();
    expect(
      screen.getByText('Ghost members — consuming seats with no activity'),
    ).toBeInTheDocument();
    // Find the ghost member table section by title, then locate the table that follows
    const sectionTitle = screen.getByText('Ghost members — consuming seats with no activity');
    const tableWrap = sectionTitle.nextElementSibling as HTMLElement;
    const table = tableWrap?.querySelector('table') as HTMLElement;
    expect(table).toBeTruthy();
    const thead = table.querySelector('thead')!;
    const firstRow = thead.querySelectorAll('tr')[0];
    const headers = firstRow.querySelectorAll('th');
    expect(headers).toHaveLength(2);
    expect(headers[0].textContent).toContain('Member');
    expect(headers[1].textContent).toContain('Last active');
  });

  it('renders ghost members from API data', () => {
    renderWithProviders();
    expect(screen.getByText('legacy-bot-1')).toBeInTheDocument();
    expect(screen.getByText('old-dev-2')).toBeInTheDocument();
    expect(screen.getByText('Never')).toBeInTheDocument();
  });

  it('shows "No ghost members detected" when empty', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({
      data: mockLicenseConsumption,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: mockSeatData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: mockCopilotData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: { ghost_members: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderWithProviders();
    expect(screen.getByText('No ghost members detected')).toBeInTheDocument();
  });

  it('renders copilot cross-reference section', () => {
    renderWithProviders();
    expect(screen.getByText('Copilot seat cross-reference')).toBeInTheDocument();
    expect(screen.getByText(/45 Copilot seats/)).toBeInTheDocument();
  });

  it('renders data source note', () => {
    renderWithProviders();
    expect(screen.getByText(/License seat data is derived from/)).toBeInTheDocument();
  });

  it('renders summary MetricCards (Seat utilization, Ghost members, Active seats, Copilot seats)', () => {
    renderWithProviders();
    expect(screen.getByText('Seat utilization')).toBeInTheDocument();
    const ghostLabels = screen.getAllByText('Ghost members');
    expect(ghostLabels.length).toBeGreaterThanOrEqual(2);
    const activeLabels = screen.getAllByText('Active seats');
    expect(activeLabels.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Copilot seats')).toBeInTheDocument();
  });

  it('shows loading spinner for ghost members', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({
      data: mockLicenseConsumption,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: mockSeatData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: mockCopilotData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() });
    renderWithProviders();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('shows error banner for ghost members on error', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({
      data: mockLicenseConsumption,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: mockSeatData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: mockCopilotData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: true, refetch: vi.fn() });
    renderWithProviders();
    expect(screen.getByText('Failed to load ghost members')).toBeInTheDocument();
  });

  it('shows sample data banner when all API queries return empty data', () => {
    mockQueryReturns.length = 0;
    // All queries return empty/no data (license consumption with 0 seats = no GHEC data)
    mockQueryReturns.push({
      data: { total_seats_purchased: 0 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: { data: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: { data: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: { ghost_members: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderWithProviders();
    expect(screen.getByText(/No license data found/)).toBeInTheDocument();
  });

  it('does not show sample data banner when real data is available', () => {
    renderWithProviders();
    expect(screen.queryByText(/No license data found/)).not.toBeInTheDocument();
  });

  it('does not show sample data banner during loading state', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() });
    renderWithProviders();
    expect(screen.queryByText(/No license data found/)).not.toBeInTheDocument();
  });

  it('does not show sample data banner during error state', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: true, refetch: vi.fn() });
    renderWithProviders();
    expect(screen.queryByText(/No license data found/)).not.toBeInTheDocument();
  });

  it('uses GHEC license data when available', () => {
    renderWithProviders();
    // Should show the synced_at info from GHEC data
    expect(screen.getByText(/consumed-licenses/)).toBeInTheDocument();
  });

  it('falls back to report data when GHEC license data unavailable', () => {
    mockQueryReturns.length = 0;
    // License consumption with 0 purchased seats (no GHEC data)
    mockQueryReturns.push({
      data: { ...mockLicenseConsumption, total_seats_purchased: 0 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: mockSeatData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: mockCopilotData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    mockQueryReturns.push({
      data: mockGhostMembers,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderWithProviders();
    // Falls back to showing report-derived source note (not GHEC API)
    expect(screen.queryByText(/consumed-licenses/)).not.toBeInTheDocument();
    const addMemberRefs = screen.getAllByText(/org\.add_member/);
    expect(addMemberRefs.length).toBeGreaterThanOrEqual(1);
  });

  it('renders GHEC License Consumption section header', () => {
    renderWithProviders();
    expect(screen.getByText('GHEC License Consumption')).toBeInTheDocument();
  });

  it('renders Copilot License Usage section header', () => {
    renderWithProviders();
    expect(screen.getByText('Copilot License Usage')).toBeInTheDocument();
  });

  it('renders clickable metric cards with role=button', () => {
    renderWithProviders();
    // Only the Ghost members MetricCard has a click handler (drill-down to ghost member detail).
    // Use getAllByText since "Ghost members" appears in both the card title and the metric label.
    const ghostMembersElements = screen.getAllByText('Ghost members');
    const clickableGhostCard = ghostMembersElements
      .map((el) => el.closest('[role="button"]'))
      .find((el) => el !== null);
    expect(clickableGhostCard).toBeInTheDocument();
  });
});
