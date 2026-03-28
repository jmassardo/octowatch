import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { LicensePane } from './LicensePane';
import { COST_PER_SEAT_DEFAULT } from './healthData';

vi.mock('../../api/reports', () => ({
  getSeatUtilizationReport: vi.fn(),
  getCopilotSeatsReport: vi.fn(),
}));

vi.mock('../../api/healthSignals', () => ({
  getGhostMembers: vi.fn(),
}));

const mockSeatData = {
  data: [
    { provisioned_seat_count: 100, active_seat_count: 82, utilization_pct: 82 },
  ],
};

const mockCopilotData = {
  data: [
    { seats_net: 45 },
  ],
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
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQuery: () => {
      const idx = useQueryCallIndex++;
      return mockQueryReturns[idx] || { data: undefined, isLoading: false, isError: false, refetch: vi.fn() };
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
      <MemoryRouter>
        <LicensePane />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function setDefaultData() {
  mockQueryReturns.length = 0;
  // Call 0: seat utilization
  mockQueryReturns.push({ data: mockSeatData, isLoading: false, isError: false, refetch: vi.fn() });
  // Call 1: copilot seats
  mockQueryReturns.push({ data: mockCopilotData, isLoading: false, isError: false, refetch: vi.fn() });
  // Call 2: ghost members
  mockQueryReturns.push({ data: mockGhostMembers, isLoading: false, isError: false, refetch: vi.fn() });
}

describe('LicensePane', () => {
  beforeEach(() => {
    setDefaultData();
  });

  it('renders total seats card', () => {
    renderWithProviders();
    expect(screen.getByText('Total seats (GitHub)')).toBeInTheDocument();
    expect(screen.getByText('/ 100')).toBeInTheDocument();
    expect(screen.getByText(/82% utilized/)).toBeInTheDocument();
  });

  it('renders ghost members card with count', () => {
    renderWithProviders();
    const ghostTexts = screen.getAllByText('Ghost members');
    expect(ghostTexts.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Dormant 90d+ still consuming a seat')).toBeInTheDocument();
    const expectedCost = 2 * COST_PER_SEAT_DEFAULT;
    expect(screen.getByText(`≈ $${expectedCost}/month recoverable`)).toBeInTheDocument();
  });

  it('renders Active seats card', () => {
    renderWithProviders();
    const activeLabels = screen.getAllByText('Active seats');
    expect(activeLabels.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Members with recent activity')).toBeInTheDocument();
  });

  it('renders ghost member table with 2 columns (Member, Last active)', () => {
    renderWithProviders();
    expect(screen.getByText('Ghost members — consuming seats with no activity')).toBeInTheDocument();
    const table = screen.getByText('Member').closest('table')!;
    const headers = within(table).getAllByRole('columnheader');
    expect(headers).toHaveLength(2);
    expect(headers.map((h) => h.textContent)).toEqual(['Member', 'Last active']);
  });

  it('renders ghost members from API data', () => {
    renderWithProviders();
    expect(screen.getByText('legacy-bot-1')).toBeInTheDocument();
    expect(screen.getByText('old-dev-2')).toBeInTheDocument();
    expect(screen.getByText('Never')).toBeInTheDocument();
  });

  it('shows "No ghost members detected" when empty', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({ data: mockSeatData, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: mockCopilotData, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: { ghost_members: [] }, isLoading: false, isError: false, refetch: vi.fn() });
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
    mockQueryReturns.push({ data: mockSeatData, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: mockCopilotData, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() });
    renderWithProviders();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('shows error banner for ghost members on error', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({ data: mockSeatData, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: mockCopilotData, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: true, refetch: vi.fn() });
    renderWithProviders();
    expect(screen.getByText('Failed to load ghost members')).toBeInTheDocument();
  });
});
