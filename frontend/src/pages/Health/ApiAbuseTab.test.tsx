import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ApiAbuseTab } from './ApiAbuseTab';

vi.mock('../../api/healthSignals', () => ({
  getApiAbuseSignals: vi.fn(),
}));

const mockAbuseData = {
  signals: [
    {
      signal_type: 'rate_limit_violation',
      severity: 'critical',
      actor: 'bot-user',
      event_count: 15,
      time_window_start: '2025-01-01T00:00:00Z',
      time_window_end: '2025-01-01T01:00:00Z',
      details: '15 rate limit events in 1 hour',
      recommended_action: 'Review API usage patterns',
    },
    {
      signal_type: 'failed_auth',
      severity: 'high',
      actor: 'unknown-actor',
      event_count: 8,
      time_window_start: '2025-01-01T02:00:00Z',
      time_window_end: '2025-01-01T03:00:00Z',
      details: '8 failed auth attempts in 1 hour',
      recommended_action: 'Investigate and block if malicious',
    },
  ],
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
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ApiAbuseTab />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ApiAbuseTab', () => {
  beforeEach(() => {
    mockQueryReturns.length = 0;
  });

  it('shows loading spinner when loading', () => {
    mockQueryReturns.push({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() });
    renderTab();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('renders metric cards with data', () => {
    mockQueryReturns.push({
      data: mockAbuseData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText('Total abuse signals')).toBeInTheDocument();
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('High severity')).toBeInTheDocument();
    expect(screen.getByText('Actors affected')).toBeInTheDocument();
  });

  it('renders table with abuse signals', () => {
    mockQueryReturns.push({
      data: mockAbuseData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText('bot-user')).toBeInTheDocument();
    expect(screen.getByText('unknown-actor')).toBeInTheDocument();
  });

  it('shows empty state when no signals', () => {
    mockQueryReturns.push({
      data: { signals: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText(/No API abuse signals detected/)).toBeInTheDocument();
  });

  it('renders source note', () => {
    mockQueryReturns.push({
      data: { signals: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText(/Derived from/)).toBeInTheDocument();
  });
});
