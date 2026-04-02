import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SecurityPosturePane } from './SecurityPosturePane';
import type {
  SecurityPostureResponse,
  SecretScanningResponse,
  SsoHealthResponse,
  PrivilegeChangesResponse,
} from '../../api/healthSignals';

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

const mockPostureData: SecurityPostureResponse = {
  repos_with_secret_scanning: 42,
  repos_with_dependabot: 38,
  repos_with_codeql: 25,
  repos_with_ghas: 30,
  features_disabled_count: 3,
};

const mockSecretData: SecretScanningResponse = {
  unresolved_total: 12,
  publicly_leaked: 2,
  open_gt_7d: 8,
  open_gt_30d: 4,
  mttr_hours: 48,
};

const mockSsoData: SsoHealthResponse = {
  orgs: [
    { org: 'acme-corp', sso_enabled: true },
    { org: 'globex', sso_enabled: false },
  ],
};

const mockPrivilegeData: PrivilegeChangesResponse = {
  admin_promotions: 5,
  integration_manager_grants: 2,
  custom_role_changes: 7,
};

interface MockQueryReturn<T> {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  refetch: ReturnType<typeof vi.fn>;
}

let queryResults: Record<string, MockQueryReturn<unknown>>;

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query');
  return {
    ...actual,
    useQuery: (opts: { queryKey: string[] }) => {
      const key = opts.queryKey.join('/');
      return queryResults[key] ?? { data: undefined, isLoading: true, isError: false, refetch: vi.fn() };
    },
  };
});

function renderPane() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SecurityPosturePane />
    </QueryClientProvider>,
  );
}

describe('SecurityPosturePane', () => {
  beforeEach(() => {
    queryResults = {
      'health/security-posture': { data: mockPostureData, isLoading: false, isError: false, refetch: vi.fn() },
      'health/secret-scanning': { data: mockSecretData, isLoading: false, isError: false, refetch: vi.fn() },
      'health/sso': { data: mockSsoData, isLoading: false, isError: false, refetch: vi.fn() },
      'health/privilege-changes': { data: mockPrivilegeData, isLoading: false, isError: false, refetch: vi.fn() },
    };
  });

  it('renders loading spinner when any query is loading', () => {
    queryResults['health/security-posture'] = { data: undefined, isLoading: true, isError: false, refetch: vi.fn() };
    renderPane();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('renders error banner when any query fails', () => {
    queryResults['health/secret-scanning'] = { data: undefined, isLoading: false, isError: true, refetch: vi.fn() };
    renderPane();
    expect(screen.getByText('Failed to load security posture data')).toBeInTheDocument();
  });

  it('renders the sample data banner', () => {
    renderPane();
    expect(
      screen.getByText(/Security posture signals are derived from audit log events/),
    ).toBeInTheDocument();
  });

  /* ---- Security Coverage Summary ---- */

  it('renders security coverage summary section', () => {
    renderPane();
    expect(screen.getByText('Security coverage summary')).toBeInTheDocument();
  });

  it('renders security coverage metric values', () => {
    renderPane();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('Secret scanning enabled')).toBeInTheDocument();
    expect(screen.getByText('38')).toBeInTheDocument();
    expect(screen.getByText('Dependabot enabled')).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument();
    expect(screen.getByText('CodeQL enabled')).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
    expect(screen.getByText('GHAS enabled')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Features disabled')).toBeInTheDocument();
  });

  /* ---- Secret Scanning Alerts ---- */

  it('renders secret scanning alerts section', () => {
    renderPane();
    expect(screen.getByText('Secret scanning alerts')).toBeInTheDocument();
  });

  it('renders secret scanning metric values', () => {
    renderPane();
    expect(screen.getByText('Unresolved total')).toBeInTheDocument();
    expect(screen.getByText('Publicly leaked')).toBeInTheDocument();
    expect(screen.getByText('Open > 7 days')).toBeInTheDocument();
    expect(screen.getByText('Open > 30 days')).toBeInTheDocument();
    expect(screen.getByText('MTTR')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('renders MTTR in days format when >= 24h', () => {
    renderPane();
    expect(screen.getByText('2d')).toBeInTheDocument();
  });

  /* ---- SSO Status ---- */

  it('renders SSO status table', () => {
    renderPane();
    expect(screen.getByText('SSO status by organization')).toBeInTheDocument();
  });

  it('renders org names in SSO table', () => {
    renderPane();
    expect(screen.getByText('acme-corp')).toBeInTheDocument();
    expect(screen.getByText('globex')).toBeInTheDocument();
  });

  it('renders SSO enabled/disabled labels', () => {
    renderPane();
    expect(screen.getByText('enabled')).toBeInTheDocument();
    expect(screen.getByText('disabled')).toBeInTheDocument();
  });

  /* ---- Privilege Changes ---- */

  it('renders privilege changes section', () => {
    renderPane();
    expect(screen.getByText('Privilege changes (30d)')).toBeInTheDocument();
  });

  it('renders privilege change metric values', () => {
    renderPane();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('Admin promotions')).toBeInTheDocument();
    expect(screen.getByText('Integration manager grants')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('Custom role changes')).toBeInTheDocument();
  });

  /* ---- Audit Stream Status ---- */

  it('renders audit stream status', () => {
    renderPane();
    expect(screen.getByText('Audit stream status')).toBeInTheDocument();
    expect(screen.getByText('active')).toBeInTheDocument();
  });

  it('shows SSO org count in stream status', () => {
    renderPane();
    expect(screen.getByText(/1\/2 orgs with SSO/)).toBeInTheDocument();
  });

  /* ---- Empty SSO state ---- */

  it('renders empty state when no SSO orgs', () => {
    queryResults['health/sso'] = {
      data: { orgs: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    expect(screen.getByText('No SSO data available')).toBeInTheDocument();
  });

  /* ---- Zero values ---- */

  it('renders zero values when data returns zeros', () => {
    queryResults['health/security-posture'] = {
      data: {
        repos_with_secret_scanning: 0,
        repos_with_dependabot: 0,
        repos_with_codeql: 0,
        repos_with_ghas: 0,
        features_disabled_count: 0,
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    // All the "0" values rendered as metric cards
    const zeros = screen.getAllByText('0');
    expect(zeros.length).toBeGreaterThanOrEqual(5);
  });

  /* ---- SSO Drill-down ---- */

  it('opens SSO drill-down modal when SSO count is clicked', () => {
    renderPane();
    const ssoDrilldown = screen.getByRole('button', {
      name: /orgs with SSO.*click to view/i,
    });
    fireEvent.click(ssoDrilldown);
    // Modal opened — close button appears
    expect(screen.getByLabelText('Close')).toBeInTheDocument();
    // Title appears twice: once in the section title, once in the modal
    const titles = screen.getAllByText('SSO status by organization');
    expect(titles.length).toBe(2);
  });

  it('shows SSO org data in drill-down modal', () => {
    renderPane();
    const ssoDrilldown = screen.getByRole('button', {
      name: /orgs with SSO/i,
    });
    fireEvent.click(ssoDrilldown);
    // Modal should show column headers
    const orgHeaders = screen.getAllByText('Organization');
    expect(orgHeaders.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('SSO Status')).toBeInTheDocument();
  });

  it('closes SSO drill-down modal when close button is clicked', () => {
    renderPane();
    const ssoDrilldown = screen.getByRole('button', {
      name: /orgs with SSO/i,
    });
    fireEvent.click(ssoDrilldown);
    const closeBtn = screen.getByLabelText('Close');
    fireEvent.click(closeBtn);
    expect(screen.queryByLabelText('Close')).not.toBeInTheDocument();
  });

  it('SSO drill-down stat is keyboard accessible', () => {
    renderPane();
    const ssoDrilldown = screen.getByRole('button', {
      name: /orgs with SSO/i,
    });
    fireEvent.keyDown(ssoDrilldown, { key: 'Enter' });
    expect(screen.getByLabelText('Close')).toBeInTheDocument();
  });
});
