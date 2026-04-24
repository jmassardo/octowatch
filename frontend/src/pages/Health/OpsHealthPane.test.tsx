import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { OpsHealthPane } from './OpsHealthPane';
import type {
  WorkflowHealthResponse,
  BranchProtectionResponse,
  CopilotGovernanceResponse,
  CodespacesResponse,
  RunnerHealthResponse,
} from '../../api/healthSignals';

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

const mockWorkflowData: WorkflowHealthResponse = {
  workflows: [
    {
      repo: 'acme/api',
      workflow_name: 'ci.yml',
      total_runs: 100,
      successes: 85,
      failures: 15,
      failure_rate_pct: 15.0,
      last_run: '2025-03-15T10:00:00Z',
    },
    {
      repo: 'acme/web',
      workflow_name: 'deploy.yml',
      total_runs: 50,
      successes: 48,
      failures: 2,
      failure_rate_pct: 4.0,
      last_run: '2025-03-14T08:00:00Z',
    },
  ],
};

const mockBranchData: BranchProtectionResponse = {
  protections_removed: 3,
  policy_overrides: 7,
  modified: 12,
  distinct_repos_affected: 5,
};

const mockCopilotData: CopilotGovernanceResponse = {
  seats_granted_90d: 20,
  seats_removed: 4,
  unique_users: 45,
};

const mockCodespacesData: CodespacesResponse = {
  active_never_suspended: 6,
  large_machine_count: 2,
  unique_users: 18,
};

const mockRunnerData: RunnerHealthResponse = {
  runners: [
    {
      org: 'acme',
      runner_name: 'runner-01',
      version: '2.311.0',
      group: 'default',
      last_event: '2025-03-15T12:00:00Z',
    },
    {
      org: 'globex',
      runner_name: 'runner-02',
      version: '2.310.0',
      group: 'gpu',
      last_event: '2025-03-14T06:00:00Z',
    },
  ],
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
      <OpsHealthPane />
    </QueryClientProvider>,
  );
}

describe('OpsHealthPane', () => {
  beforeEach(() => {
    queryResults = {
      'health/workflows': {
        data: mockWorkflowData,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'health/branch-protection': {
        data: mockBranchData,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'health/copilot-governance': {
        data: mockCopilotData,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'health/codespaces': {
        data: mockCodespacesData,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'health/runners': {
        data: mockRunnerData,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
  });

  it('renders loading spinner when any query is loading', () => {
    queryResults['health/workflows'] = {
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('renders error banner when any query fails', () => {
    queryResults['health/runners'] = {
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    };
    renderPane();
    expect(screen.getByText('Failed to load operations health data')).toBeInTheDocument();
  });

  it('renders the workflow health section subtitle', () => {
    renderPane();
    expect(screen.getByText(/Per-workflow run metrics derived from/)).toBeInTheDocument();
  });

  /* ---- Workflow Health Table ---- */

  it('renders workflow health section', () => {
    renderPane();
    expect(screen.getByText('Workflow health')).toBeInTheDocument();
  });

  it('renders workflow table rows', () => {
    renderPane();
    expect(screen.getByText('acme/api')).toBeInTheDocument();
    expect(screen.getByText('ci.yml')).toBeInTheDocument();
    expect(screen.getByText('acme/web')).toBeInTheDocument();
    expect(screen.getByText('deploy.yml')).toBeInTheDocument();
  });

  it('renders failure rate labels with correct variants', () => {
    renderPane();
    // 15% > 10 → attention
    expect(screen.getByText('15.0%')).toBeInTheDocument();
    // 4% < 10 → success
    expect(screen.getByText('4.0%')).toBeInTheDocument();
  });

  it('renders workflow run counts', () => {
    renderPane();
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.getByText('85')).toBeInTheDocument();
    expect(screen.getByText('15')).toBeInTheDocument();
  });

  /* ---- Branch Protection ---- */

  it('renders branch protection section', () => {
    renderPane();
    expect(screen.getByText('Branch protection changes (30d)')).toBeInTheDocument();
  });

  it('renders branch protection metric values', () => {
    renderPane();
    expect(screen.getByText('Protections removed')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Policy overrides')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('Repos affected')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  /* ---- Copilot Governance ---- */

  it('renders copilot governance section', () => {
    renderPane();
    expect(screen.getByText('Copilot governance')).toBeInTheDocument();
  });

  it('renders copilot governance metrics', () => {
    renderPane();
    expect(screen.getByText('Seats granted (90d)')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
    expect(screen.getByText('Seats removed')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('45')).toBeInTheDocument();
  });

  /* ---- Codespace Activity ---- */

  it('renders codespace activity section', () => {
    renderPane();
    expect(screen.getByText('Codespace activity')).toBeInTheDocument();
  });

  it('renders codespace activity metrics', () => {
    renderPane();
    expect(screen.getByText('Active never suspended')).toBeInTheDocument();
    expect(screen.getByText('6')).toBeInTheDocument();
    expect(screen.getByText('Large machine count')).toBeInTheDocument();
    // '2' appears in multiple places (runner version "2.310.0" etc.), use getAllByText
    expect(screen.getAllByText('2').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('18')).toBeInTheDocument();
  });

  /* ---- Runner Fleet ---- */

  it('renders runner fleet section', () => {
    renderPane();
    expect(screen.getByText('Runner fleet')).toBeInTheDocument();
  });

  it('renders runner table rows', () => {
    renderPane();
    expect(screen.getByText('runner-01')).toBeInTheDocument();
    expect(screen.getByText('2.311.0')).toBeInTheDocument();
    expect(screen.getByText('default')).toBeInTheDocument();
    expect(screen.getByText('runner-02')).toBeInTheDocument();
    expect(screen.getByText('gpu')).toBeInTheDocument();
  });

  /* ---- Empty states ---- */

  it('renders empty state for workflows', () => {
    queryResults['health/workflows'] = {
      data: { workflows: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    expect(screen.getByText('No workflow data available')).toBeInTheDocument();
  });

  it('renders empty state for runners', () => {
    queryResults['health/runners'] = {
      data: { runners: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    expect(screen.getByText('No runner data available')).toBeInTheDocument();
  });
});
