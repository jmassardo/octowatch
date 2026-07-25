import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { SecurityTab } from './SecurityTab';

vi.mock('../../api/healthSignals', () => ({
  getPlatformSecurity: vi.fn(),
}));

const mockSecurityData = {
  orgs: [
    {
      org: 'acme-corp',
      sso_configured: true,
      two_fa_required: true,
      audit_log_streaming: false,
      ip_allowlist_configured: true,
      branch_protection_default: true,
      compliance_score: 80,
      recommendations: ['Enable audit log streaming'],
    },
    {
      org: 'globex',
      sso_configured: false,
      two_fa_required: false,
      audit_log_streaming: false,
      ip_allowlist_configured: false,
      branch_protection_default: false,
      compliance_score: 0,
      recommendations: [
        'Enable SSO',
        'Require 2FA',
        'Enable audit log streaming',
        'Configure IP allowlist',
        'Set up branch protection defaults',
      ],
    },
  ],
  overall_compliance_score: 40,
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
        <SecurityTab />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SecurityTab', () => {
  beforeEach(() => {
    mockQueryReturns.length = 0;
  });

  it('shows loading spinner when loading', () => {
    mockQueryReturns.push({ data: undefined, isLoading: true, isError: false, refetch: vi.fn() });
    renderTab();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('renders org security cards', () => {
    mockQueryReturns.push({
      data: mockSecurityData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText('acme-corp')).toBeInTheDocument();
    expect(screen.getByText('globex')).toBeInTheDocument();
  });

  it('renders compliance metrics', () => {
    mockQueryReturns.push({
      data: mockSecurityData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText('Overall compliance')).toBeInTheDocument();
    expect(screen.getByText('SSO enabled')).toBeInTheDocument();
    // "2FA required" appears both as MetricCard label and checklist item
    expect(screen.getAllByText('2FA required').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Security gaps')).toBeInTheDocument();
  });

  it('renders security checklist items', () => {
    mockQueryReturns.push({
      data: mockSecurityData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getAllByText('SSO configured').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('2FA required').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Audit log streaming').length).toBeGreaterThanOrEqual(1);
  });

  it('renders recommendations', () => {
    mockQueryReturns.push({
      data: mockSecurityData,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getAllByText('Recommendations').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Enable SSO')).toBeInTheDocument();
  });

  it('shows empty state when no orgs', () => {
    mockQueryReturns.push({
      data: { orgs: [], overall_compliance_score: 0 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText(/No platform security data available/)).toBeInTheDocument();
  });

  it('renders source note', () => {
    mockQueryReturns.push({
      data: { orgs: [], overall_compliance_score: 0 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab();
    expect(screen.getByText(/Derived from/)).toBeInTheDocument();
  });
});
