import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RepoHealthPane } from './RepoHealthPane';
import type { RepoHealthResponse } from '../../api/healthSignals';

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts-mock" />,
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

const mockRepoHealthData: RepoHealthResponse = {
  stale: [
    {
      org: 'acme-corp',
      repo: 'legacy-payments',
      last_event_at: '2024-01-15T00:00:00Z',
      days_since_activity: 389,
    },
    {
      org: 'acme-corp',
      repo: 'infra-deploy',
      last_event_at: '2025-03-10T00:00:00Z',
      days_since_activity: 2,
    },
    {
      org: 'globex',
      repo: 'internal-tools',
      last_event_at: '2025-02-01T00:00:00Z',
      days_since_activity: 47,
    },
    {
      org: 'acme-corp',
      repo: 'old-api',
      last_event_at: '2024-06-15T00:00:00Z',
      days_since_activity: 200,
    },
  ],
  archived: [
    {
      org: 'acme-corp',
      repo: 'deprecated-tool',
      archived_at: '2025-01-10T00:00:00Z',
      archived_by: 'admin-user',
      days_since_archived: 60,
    },
  ],
  abandoned_forks: [
    {
      actor: 'dev-user',
      org: 'globex',
      repo: 'forked-lib',
      forked_at: '2024-11-01T00:00:00Z',
      days_since_fork: 130,
    },
  ],
};

let mockQueryReturn: {
  data: RepoHealthResponse | undefined;
  isLoading: boolean;
  isError: boolean;
  refetch: ReturnType<typeof vi.fn>;
};

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQuery: () => mockQueryReturn,
  };
});

function renderPane() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <RepoHealthPane />
    </QueryClientProvider>,
  );
}

describe('RepoHealthPane', () => {
  beforeEach(() => {
    mockQueryReturn = {
      data: mockRepoHealthData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
  });

  it('renders loading spinner when data is loading', () => {
    mockQueryReturn = { data: undefined, isLoading: true, isError: false, refetch: vi.fn() };
    renderPane();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('renders error banner when query fails', () => {
    mockQueryReturn = { data: undefined, isLoading: false, isError: true, refetch: vi.fn() };
    renderPane();
    expect(screen.getByText('Failed to load repository health data')).toBeInTheDocument();
  });

  it('renders repo count in toolbar', () => {
    renderPane();
    expect(screen.getByText(/4 repos/)).toBeInTheDocument();
  });

  it('renders the sample data banner', () => {
    renderPane();
    expect(
      screen.getByText(/Branch protection, secret scanning, Dependabot/),
    ).toBeInTheDocument();
  });

  it('renders repository names in the table', () => {
    renderPane();
    // legacy-payments appears in both table and archive candidates
    expect(screen.getAllByText('acme-corp/legacy-payments').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('acme-corp/infra-deploy')).toBeInTheDocument();
    expect(screen.getByText('globex/internal-tools')).toBeInTheDocument();
  });

  it('renders health labels for repos', () => {
    renderPane();
    // legacy-payments with 389 days should be critical
    expect(screen.getByText('⚠ critical')).toBeInTheDocument();
  });

  it('renders last push days in the table', () => {
    renderPane();
    expect(screen.getByText('389 days')).toBeInTheDocument();
    expect(screen.getByText('2 days')).toBeInTheDocument();
    expect(screen.getByText('47 days')).toBeInTheDocument();
  });

  it('renders unknown labels for columns without audit data', () => {
    renderPane();
    const unknownLabels = screen.getAllByText('unknown');
    // Each repo should have unknown for branch protection, secret scanning, dependabot, CI = 4 per repo * 4 repos
    expect(unknownLabels.length).toBe(16);
  });

  it('renders the stale trend section title', () => {
    renderPane();
    expect(
      screen.getByText('Stale repository trend — last 6 months'),
    ).toBeInTheDocument();
  });

  it('renders the ECharts chart mock', () => {
    renderPane();
    const charts = screen.getAllByTestId('echarts-mock');
    expect(charts.length).toBeGreaterThanOrEqual(1);
  });

  it('renders unhealthy summary cards', () => {
    renderPane();
    expect(
      screen.getByText('Repos with no branch protection on default branch'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Repos with secret scanning disabled'),
    ).toBeInTheDocument();
  });

  it('renders archive/delete candidates section', () => {
    renderPane();
    expect(screen.getByText('Archive / delete candidates')).toBeInTheDocument();
  });

  it('renders archived repos in candidates', () => {
    renderPane();
    expect(screen.getByText('acme-corp/deprecated-tool')).toBeInTheDocument();
    expect(screen.getByText('archived')).toBeInTheDocument();
  });

  it('renders abandoned forks in candidates', () => {
    renderPane();
    expect(screen.getByText('globex/forked-lib')).toBeInTheDocument();
    expect(screen.getByText('abandoned fork')).toBeInTheDocument();
  });

  it('renders empty state when no repos', () => {
    mockQueryReturn = {
      data: { stale: [], archived: [], abandoned_forks: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    expect(screen.getByText('No stale repositories found')).toBeInTheDocument();
    expect(screen.getByText('No archive candidates found.')).toBeInTheDocument();
  });

  it('renders singular "repo" when count is 1', () => {
    mockQueryReturn = {
      data: {
        stale: [mockRepoHealthData.stale[0]],
        archived: [],
        abandoned_forks: [],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    expect(screen.getByText(/1 repo/)).toBeInTheDocument();
  });
});
