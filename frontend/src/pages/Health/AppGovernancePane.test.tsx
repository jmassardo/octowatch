import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppGovernancePane } from './AppGovernancePane';
import type {
  AppGovernanceResponse,
  CodeScanningResponse,
  VulnerabilitiesResponse,
} from '../../api/healthSignals';

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

const mockAppData: AppGovernanceResponse = {
  apps_installed: 10,
  apps_removed: 3,
  oauth_approved: 15,
  oauth_denied: 2,
  token_revocations: 5,
  webhooks_created: 8,
  webhooks_removed: 4,
  webhooks_modified: 6,
};

const mockCodeScanData: CodeScanningResponse = {
  total_alerts: 24,
  avg_hours_to_close: 72,
  dismissed_count: 5,
  reappeared_count: 3,
};

const mockVulnData: VulnerabilitiesResponse = {
  total_open: 18,
  critical_open: 4,
  high_open: 7,
  open_gt_30d: 9,
  critical_open_gt_14d: 2,
  avg_open_days: 45,
};

interface MockQueryReturn<T> {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  refetch: ReturnType<typeof vi.fn>;
}

let queryResults: Record<string, MockQueryReturn<unknown>>;

vi.mock('@tanstack/react-query', async () => {
  const actual =
    await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQuery: (opts: { queryKey: string[] }) => {
      const key = opts.queryKey.join('/');
      return (
        queryResults[key] ?? { data: undefined, isLoading: true, isError: false, refetch: vi.fn() }
      );
    },
  };
});

function renderPane() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AppGovernancePane />
    </QueryClientProvider>,
  );
}

describe('AppGovernancePane', () => {
  beforeEach(() => {
    queryResults = {
      'health/app-governance': {
        data: mockAppData,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'health/code-scanning': {
        data: mockCodeScanData,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'health/vulnerabilities': {
        data: mockVulnData,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
  });

  it('renders loading spinner when any query is loading', () => {
    queryResults['health/app-governance'] = {
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('renders error banner when any query fails', () => {
    queryResults['health/code-scanning'] = {
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    };
    renderPane();
    expect(screen.getByText('Failed to load app governance data')).toBeInTheDocument();
  });

  it('does not render a sample data banner', () => {
    renderPane();
    expect(
      screen.queryByText(/App governance signals are derived from audit log events/),
    ).not.toBeInTheDocument();
  });

  /* ---- OAuth & App Summary ---- */

  it('renders OAuth & app summary section', () => {
    renderPane();
    expect(screen.getByText('OAuth & app summary (90d)')).toBeInTheDocument();
  });

  it('renders app metric values', () => {
    renderPane();
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('Apps installed')).toBeInTheDocument();
    expect(screen.getByText('Apps removed')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();
    expect(screen.getByText('OAuth approved')).toBeInTheDocument();
    expect(screen.getByText('OAuth denied')).toBeInTheDocument();
    expect(screen.getByText('Token revocations')).toBeInTheDocument();
  });

  /* ---- Code Scanning Health ---- */

  it('renders code scanning health section', () => {
    renderPane();
    expect(screen.getByText('Code scanning health')).toBeInTheDocument();
  });

  it('renders code scanning metrics', () => {
    renderPane();
    expect(screen.getByText('Total alerts')).toBeInTheDocument();
    expect(screen.getByText('24')).toBeInTheDocument();
    expect(screen.getByText('Avg hours to close')).toBeInTheDocument();
    expect(screen.getByText('72h')).toBeInTheDocument();
    expect(screen.getByText('Dismissed')).toBeInTheDocument();
    expect(screen.getByText('Reappeared')).toBeInTheDocument();
  });

  /* ---- Vulnerability Aging ---- */

  it('renders vulnerability aging section', () => {
    renderPane();
    expect(screen.getByText('Vulnerability aging')).toBeInTheDocument();
  });

  it('renders vulnerability metrics', () => {
    renderPane();
    expect(screen.getByText('Total open')).toBeInTheDocument();
    expect(screen.getByText('18')).toBeInTheDocument();
    expect(screen.getByText('Critical open')).toBeInTheDocument();
    expect(screen.getByText('High open')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('Open > 30 days')).toBeInTheDocument();
    expect(screen.getByText('9')).toBeInTheDocument();
    expect(screen.getByText('Critical > 14 days')).toBeInTheDocument();
    expect(screen.getByText('Avg open days')).toBeInTheDocument();
    expect(screen.getByText('45d')).toBeInTheDocument();
  });

  /* ---- Webhook Activity ---- */

  it('renders webhook activity section', () => {
    renderPane();
    expect(screen.getByText('Webhook activity (30d)')).toBeInTheDocument();
  });

  it('renders webhook metrics', () => {
    renderPane();
    expect(screen.getByText('Created')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('Removed')).toBeInTheDocument();
    expect(screen.getByText('Modified')).toBeInTheDocument();
    expect(screen.getByText('6')).toBeInTheDocument();
  });

  /* ---- Zero values ---- */

  it('renders zero values when data returns zeros', () => {
    queryResults['health/app-governance'] = {
      data: {
        apps_installed: 0,
        apps_removed: 0,
        oauth_approved: 0,
        oauth_denied: 0,
        token_revocations: 0,
        webhooks_created: 0,
        webhooks_removed: 0,
        webhooks_modified: 0,
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    const zeros = screen.getAllByText('0');
    expect(zeros.length).toBeGreaterThanOrEqual(8);
  });
});
