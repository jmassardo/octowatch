import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MaintenancePane } from './MaintenancePane';

vi.mock('../../api/healthSignals', () => ({
  getStalePrs: vi.fn(),
  getUnhealthyHooks: vi.fn(),
  getSkippedWorkflows: vi.fn(),
}));

const mockStalePrs = {
  stale_prs: [
    {
      org: 'acme-corp',
      repo: 'web-app',
      pr_number: '42',
      title: 'Add caching layer',
      actor: 'dev1',
      opened_at: '2025-01-01T00:00:00Z',
      days_open: 127,
    },
    {
      org: 'acme-corp',
      repo: 'api-service',
      pr_number: '99',
      title: 'Fix auth bug',
      actor: 'dev2',
      opened_at: '2025-02-01T00:00:00Z',
      days_open: 62,
    },
  ],
};

const mockUnhealthyHooks = {
  unhealthy_hooks: [
    {
      org: 'acme-corp',
      repo: 'web-app',
      action: 'hook.destroy',
      actor: 'admin1',
      hook_id: null,
      app_name: 'Slack Notifier',
      config_url: null,
      created_at: '2025-03-01T00:00:00Z',
    },
    {
      org: 'globex',
      repo: 'data-svc',
      action: 'hook.config_changed',
      actor: 'ops-user',
      hook_id: '12345',
      app_name: null,
      config_url: null,
      created_at: '2025-03-02T00:00:00Z',
    },
  ],
};

const mockSkippedWorkflows = {
  skipped_workflows: [
    {
      org: 'acme-corp',
      repo: 'web-app',
      action: 'workflows.disable_workflow',
      actor: 'ci-admin',
      workflow_name: 'security-scan.yml',
      workflow_id: 'wf1',
      created_at: '2025-03-01T00:00:00Z',
    },
    {
      org: 'globex',
      repo: 'data-svc',
      action: 'workflows.delete_workflow',
      actor: 'dev1',
      workflow_name: 'deploy.yml',
      workflow_id: 'wf2',
      created_at: '2025-02-15T00:00:00Z',
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
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQuery: () => {
      const idx = useQueryCallIndex++;
      return mockQueryReturns[idx] || { data: undefined, isLoading: false, isError: false, refetch: vi.fn() };
    },
  };
});

function renderPane() {
  useQueryCallIndex = 0;
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MaintenancePane />
    </QueryClientProvider>,
  );
}

function setDefaultData() {
  mockQueryReturns.length = 0;
  // Call 0: stale PRs
  mockQueryReturns.push({ data: mockStalePrs, isLoading: false, isError: false, refetch: vi.fn() });
  // Call 1: unhealthy hooks
  mockQueryReturns.push({ data: mockUnhealthyHooks, isLoading: false, isError: false, refetch: vi.fn() });
  // Call 2: skipped workflows
  mockQueryReturns.push({ data: mockSkippedWorkflows, isLoading: false, isError: false, refetch: vi.fn() });
}

describe('MaintenancePane', () => {
  beforeEach(() => {
    setDefaultData();
  });

  it('shows loading spinner when any query is loading', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() });
    renderPane();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('renders stale PRs card with API data', () => {
    renderPane();
    expect(screen.getByText('Stale PRs')).toBeInTheDocument();
    expect(screen.getByText(/open > configured threshold/)).toBeInTheDocument();
    expect(screen.getAllByText(/acme-corp\/web-app/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/127 days open/)).toBeInTheDocument();
    expect(screen.getByText(/62 days open/)).toBeInTheDocument();
  });

  it('shows "No stale PRs detected" empty state', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({ data: { stale_prs: [] }, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: mockUnhealthyHooks, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: mockSkippedWorkflows, isLoading: false, isError: false, refetch: vi.fn() });
    renderPane();
    expect(screen.getByText('No stale PRs detected')).toBeInTheDocument();
  });

  it('renders unhealthy webhooks with API data', () => {
    renderPane();
    expect(screen.getByText('Unhealthy webhooks & apps')).toBeInTheDocument();
    expect(screen.getByText('Slack Notifier')).toBeInTheDocument();
  });

  it('shows "No unhealthy webhooks detected" empty state', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({ data: mockStalePrs, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: { unhealthy_hooks: [] }, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: mockSkippedWorkflows, isLoading: false, isError: false, refetch: vi.fn() });
    renderPane();
    expect(screen.getByText('No unhealthy webhooks detected')).toBeInTheDocument();
  });

  it('renders skipped workflows table with correct columns', () => {
    renderPane();
    expect(screen.getByText('Disabled / consistently-skipped workflows')).toBeInTheDocument();
    const table = screen.getByText('Workflow').closest('table')!;
    const headers = within(table).getAllByRole('columnheader');
    expect(headers.map((h) => h.textContent)).toEqual([
      'Workflow',
      'Repository',
      'Action',
      'Actor',
      'Date',
    ]);
  });

  it('renders skipped workflow data in table', () => {
    renderPane();
    expect(screen.getByText('security-scan.yml')).toBeInTheDocument();
    expect(screen.getByText('deploy.yml')).toBeInTheDocument();
    expect(screen.getByText('ci-admin')).toBeInTheDocument();
  });

  it('renders disabled label for disable_workflow action', () => {
    renderPane();
    const disabledLabels = screen.getAllByText('disabled');
    expect(disabledLabels.length).toBeGreaterThanOrEqual(1);
  });

  it('renders deleted label for delete_workflow action', () => {
    renderPane();
    const deletedLabels = screen.getAllByText('deleted');
    expect(deletedLabels.length).toBeGreaterThanOrEqual(1);
  });

  it('shows "No disabled or skipped workflows detected" empty state', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({ data: mockStalePrs, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: mockUnhealthyHooks, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: { skipped_workflows: [] }, isLoading: false, isError: false, refetch: vi.fn() });
    renderPane();
    expect(screen.getByText('No disabled or skipped workflows detected')).toBeInTheDocument();
  });

  it('renders source notes', () => {
    renderPane();
    const sourceNotes = screen.getAllByText(/Derived from/, { exact: false });
    expect(sourceNotes.length).toBeGreaterThanOrEqual(1);
  });

  it('shows sample data banner when all API queries return empty data', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({ data: { stale_prs: [] }, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: { unhealthy_hooks: [] }, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: { skipped_workflows: [] }, isLoading: false, isError: false, refetch: vi.fn() });
    renderPane();
    expect(screen.getByText(/This data is illustrative/)).toBeInTheDocument();
  });

  it('does not show sample data banner when real data is available', () => {
    renderPane();
    expect(screen.queryByText(/This data is illustrative/)).not.toBeInTheDocument();
  });

  it('does not show sample data banner during loading state', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() });
    renderPane();
    expect(screen.queryByText(/This data is illustrative/)).not.toBeInTheDocument();
  });

  it('does not show sample data banner when any query has an error', () => {
    mockQueryReturns.length = 0;
    mockQueryReturns.push({ data: { stale_prs: [] }, isLoading: false, isError: true, refetch: vi.fn() });
    mockQueryReturns.push({ data: { unhealthy_hooks: [] }, isLoading: false, isError: false, refetch: vi.fn() });
    mockQueryReturns.push({ data: { skipped_workflows: [] }, isLoading: false, isError: false, refetch: vi.fn() });
    renderPane();
    expect(screen.queryByText(/This data is illustrative/)).not.toBeInTheDocument();
  });
});
