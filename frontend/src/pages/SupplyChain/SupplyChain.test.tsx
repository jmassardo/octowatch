import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SupplyChainPage } from './index';
import type { SupplyChainPosture, RiskSummary, RulesListResponse } from '../../api/supplyChain';

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock('../../hooks/useHelp', () => ({
  useHelp: () => ({ helpContent: null, openHelp: vi.fn(), closeHelp: vi.fn(), isHelpOpen: false }),
}));

const mockPosture: SupplyChainPosture = {
  score: 85,
  unpinned_actions: 3,
  dependency_alerts: 5,
  risky_workflows: 1,
  rules_active: 8,
  total_detections: 10,
  critical_detections: 2,
  recent_risks: [
    {
      id: 1,
      title: 'Unpinned action detected',
      severity: 'medium',
      status: 'open',
      org: 'my-org',
      repo: 'my-org/repo1',
      triggered_at: '2024-01-01T00:00:00Z',
      rule_slug: 'action-version-pinning-violation',
    },
  ],
};

const mockRisks: RiskSummary = {
  total_risks: 15,
  by_severity: { critical: 3, high: 5, medium: 7 },
  by_type: { 'action-version-pinning-violation': 10, 'workflow-injection': 5 },
  top_repos: [{ repo: 'my-org/repo1', count: 8 }],
};

const mockRules: RulesListResponse = {
  rules: [
    {
      id: 1,
      name: 'Action Version Pinning Violation',
      slug: 'action-version-pinning-violation',
      description: 'Detects unpinned actions',
      severity: 'medium',
      confidence: 'high',
      logic_type: 'pattern',
      enabled: true,
      detection_count: 10,
    },
    {
      id: 2,
      name: 'Workflow Injection',
      slug: 'workflow-injection',
      description: 'Detects dangerous pull_request_target workflows',
      severity: 'critical',
      confidence: 'high',
      logic_type: 'pattern',
      enabled: false,
      detection_count: 5,
    },
  ],
  total: 2,
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
    useMutation: () => ({
      mutate: vi.fn(),
      data: undefined,
      isPending: false,
      isError: false,
    }),
  };
});

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SupplyChainPage />
    </QueryClientProvider>,
  );
}

describe('SupplyChainPage', () => {
  beforeEach(() => {
    queryResults = {};
  });

  it('shows spinner while loading', () => {
    queryResults = {
      'supply-chain/posture': {
        data: undefined,
        isLoading: true,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/risks': {
        data: undefined,
        isLoading: true,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/rules': {
        data: undefined,
        isLoading: true,
        isError: false,
        refetch: vi.fn(),
      },
    };
    const { container } = renderPage();
    expect(container.querySelector('.spinner')).not.toBeNull();
  });

  it('shows error banner on failure', () => {
    queryResults = {
      'supply-chain/posture': {
        data: undefined,
        isLoading: false,
        isError: true,
        refetch: vi.fn(),
      },
      'supply-chain/risks': {
        data: undefined,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/rules': {
        data: undefined,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
    renderPage();
    expect(screen.getByText(/failed to load supply chain data/i)).toBeDefined();
  });

  it('renders metric cards with posture data', () => {
    queryResults = {
      'supply-chain/posture': {
        data: mockPosture,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/risks': {
        data: mockRisks,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/rules': {
        data: mockRules,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
    renderPage();
    expect(screen.getByText('85')).toBeDefined();
    expect(screen.getByText('Supply Chain Score')).toBeDefined();
    expect(screen.getByText('3')).toBeDefined();
    expect(screen.getByText('Unpinned Actions')).toBeDefined();
    expect(screen.getByText('5')).toBeDefined();
    expect(screen.getByText('Dependency Alerts')).toBeDefined();
    expect(screen.getByText('1')).toBeDefined();
    expect(screen.getByText('Risky Workflows')).toBeDefined();
    expect(screen.getAllByText('8').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Rules Active')).toBeDefined();
  });

  it('renders risk tab by default with recent detections', () => {
    queryResults = {
      'supply-chain/posture': {
        data: mockPosture,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/risks': {
        data: mockRisks,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/rules': {
        data: mockRules,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
    renderPage();
    expect(screen.getByText('Recent detections')).toBeDefined();
    expect(screen.getByText('Unpinned action detected')).toBeDefined();
  });

  it('switches to rules tab', () => {
    queryResults = {
      'supply-chain/posture': {
        data: mockPosture,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/risks': {
        data: mockRisks,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/rules': {
        data: mockRules,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
    renderPage();
    fireEvent.click(screen.getByText('Rules'));
    expect(screen.getByText('Action Version Pinning Violation')).toBeDefined();
    expect(screen.getByText('Workflow Injection')).toBeDefined();
  });

  it('switches to workflow audit tab', () => {
    queryResults = {
      'supply-chain/posture': {
        data: mockPosture,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/risks': {
        data: mockRisks,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/rules': {
        data: mockRules,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
    renderPage();
    fireEvent.click(screen.getByText('Workflow Audit'));
    expect(screen.getByText('Analyse workflow file')).toBeDefined();
    expect(screen.getByLabelText('Workflow YAML content')).toBeDefined();
  });

  it('renders tabs with correct ARIA roles', () => {
    queryResults = {
      'supply-chain/posture': {
        data: mockPosture,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/risks': {
        data: mockRisks,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/rules': {
        data: mockRules,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
    renderPage();
    const tablist = screen.getByRole('tablist');
    expect(tablist).toBeDefined();
    const tabs = screen.getAllByRole('tab');
    expect(tabs.length).toBe(3);
  });

  it('shows empty state when no risks', () => {
    const emptyPosture = { ...mockPosture, recent_risks: [] };
    queryResults = {
      'supply-chain/posture': {
        data: emptyPosture,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/risks': {
        data: { ...mockRisks, top_repos: [] },
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/rules': {
        data: mockRules,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
    renderPage();
    expect(screen.getByText('No supply chain risks detected yet.')).toBeDefined();
  });

  it('shows top repos in risks tab', () => {
    queryResults = {
      'supply-chain/posture': {
        data: mockPosture,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/risks': {
        data: mockRisks,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
      'supply-chain/rules': {
        data: mockRules,
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      },
    };
    renderPage();
    expect(screen.getByText('Top repos by risk count')).toBeDefined();
    expect(screen.getAllByText('my-org/repo1').length).toBeGreaterThanOrEqual(1);
  });
});
