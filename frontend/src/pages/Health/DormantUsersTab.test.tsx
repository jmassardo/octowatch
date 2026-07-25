import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { DormantUsersTab } from './DormantUsersTab';

vi.mock('../../api/healthSignals', () => ({
  getDormantUsers: vi.fn(),
}));

const mockDormantData = {
  users: [
    {
      login: 'inactive-dev',
      last_activity_date: '2024-06-01T00:00:00Z',
      days_inactive: 200,
      seat_type: 'github+copilot',
      estimated_monthly_cost: 40,
      recommended_action: 'Remove seat or contact user',
    },
    {
      login: 'gone-user',
      last_activity_date: '2024-09-01T00:00:00Z',
      days_inactive: 120,
      seat_type: 'github',
      estimated_monthly_cost: 21,
      recommended_action: 'Review and consider removing',
    },
  ],
  summary: {
    total_dormant: 2,
    estimated_monthly_waste: 61,
  },
};

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

function renderTab() {
  useQueryCallIndex = 0;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DormantUsersTab />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DormantUsersTab', () => {
  beforeEach(() => {
    mockQueryReturns.length = 0;
  });

  it('shows loading spinner when loading', () => {
    mockQueryReturns.push({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() });
    renderTab();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('renders dormant user data', () => {
    mockQueryReturns.push({
      data: mockDormantData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText('Dormant users')).toBeInTheDocument();
    expect(screen.getByText('inactive-dev')).toBeInTheDocument();
    expect(screen.getByText('gone-user')).toBeInTheDocument();
  });

  it('renders cost metrics', () => {
    mockQueryReturns.push({
      data: mockDormantData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText('Est. monthly waste')).toBeInTheDocument();
    expect(screen.getByText('Est. annual waste')).toBeInTheDocument();
  });

  it('renders inactivity threshold slider', () => {
    mockQueryReturns.push({
      data: mockDormantData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText('Inactivity threshold:')).toBeInTheDocument();
    expect(screen.getByText('90 days')).toBeInTheDocument();
  });

  it('shows empty state when no dormant users', () => {
    mockQueryReturns.push({
      data: { users: [], summary: { total_dormant: 0, estimated_monthly_waste: 0 } },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText(/No dormant users detected/)).toBeInTheDocument();
  });

  it('renders source note', () => {
    mockQueryReturns.push({
      data: { users: [], summary: { total_dormant: 0, estimated_monthly_waste: 0 } },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText(/Derived from audit log event activity/)).toBeInTheDocument();
  });
});
