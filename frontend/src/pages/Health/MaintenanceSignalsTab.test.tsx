import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { MaintenanceSignalsTab } from './MaintenanceSignalsTab';

vi.mock('../../api/healthSignals', () => ({
  getMaintenanceSignals: vi.fn(),
}));

const mockMaintenanceData = {
  stale_repos: [
    {
      org: 'acme-corp',
      repo: 'legacy-app',
      last_event_at: '2024-01-01T00:00:00Z',
      days_since_activity: 400,
    },
    {
      org: 'acme-corp',
      repo: 'old-service',
      last_event_at: '2024-06-01T00:00:00Z',
      days_since_activity: 250,
    },
  ],
  empty_repos: [
    {
      org: 'globex',
      repo: 'placeholder-repo',
      created_at: '2025-01-01T00:00:00Z',
    },
  ],
  archived_candidates: [
    {
      org: 'acme-corp',
      repo: 'quiet-lib',
      event_count: 3,
      last_event_at: '2025-02-01T00:00:00Z',
      days_since_activity: 90,
    },
  ],
  summary: {
    stale_count: 2,
    empty_count: 1,
    archived_candidate_count: 1,
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
        <MaintenanceSignalsTab />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('MaintenanceSignalsTab', () => {
  beforeEach(() => {
    mockQueryReturns.length = 0;
  });

  it('shows loading spinner when loading', () => {
    mockQueryReturns.push({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() });
    renderTab();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('renders metric cards with summary data', () => {
    mockQueryReturns.push({
      data: mockMaintenanceData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    // Metric card labels (may also appear as section titles)
    expect(screen.getAllByText('Stale repos').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Empty repos').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Archive candidates/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Total issues')).toBeInTheDocument();
  });

  it('renders stale repos table', () => {
    mockQueryReturns.push({
      data: mockMaintenanceData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText(/Stale repositories \(no activity > 180 days\)/)).toBeInTheDocument();
    expect(screen.getByText(/acme-corp\/legacy-app/)).toBeInTheDocument();
  });

  it('renders empty repos section', () => {
    mockQueryReturns.push({
      data: mockMaintenanceData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText('Empty repositories')).toBeInTheDocument();
    expect(screen.getByText(/globex\/placeholder-repo/)).toBeInTheDocument();
  });

  it('renders archive candidates section', () => {
    mockQueryReturns.push({
      data: mockMaintenanceData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getAllByText('Archive candidates').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/acme-corp\/quiet-lib/)).toBeInTheDocument();
  });

  it('shows empty state when no issues', () => {
    mockQueryReturns.push({
      data: {
        stale_repos: [],
        empty_repos: [],
        archived_candidates: [],
        summary: { stale_count: 0, empty_count: 0, archived_candidate_count: 0 },
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText(/No maintenance issues detected/)).toBeInTheDocument();
  });

  it('renders source note', () => {
    mockQueryReturns.push({
      data: {
        stale_repos: [],
        empty_repos: [],
        archived_candidates: [],
        summary: { stale_count: 0, empty_count: 0, archived_candidate_count: 0 },
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText(/Derived from repository event activity patterns/)).toBeInTheDocument();
  });
});
