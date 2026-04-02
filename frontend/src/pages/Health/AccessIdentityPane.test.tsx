import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AccessIdentityPane } from './AccessIdentityPane';
import type {
  PatHealthResponse,
  BypassOffender,
  ExternalCollabResponse,
  DormantCollaborator,
} from '../../api/healthSignals';

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts-mock" />,
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

const mockPatData: PatHealthResponse = {
  summary: { no_expiry_count: 24, expired_count: 12, stale_90d_count: 7 },
  tokens: [
    {
      github_login: 'user1',
      token_name: 'deploy-token',
      token_id: 't1',
      token_type: 'classic',
      created_at: '2024-01-01T00:00:00Z',
      age_days: 400,
      signal_type: 'no_expiry',
    },
    {
      github_login: 'user2',
      token_name: 'ci-token',
      token_id: 't2',
      token_type: 'fine-grained',
      created_at: '2025-01-01T00:00:00Z',
      age_days: 60,
      signal_type: 'ok',
    },
    {
      github_login: 'user3',
      token_name: 'test-token',
      token_id: 't3',
      token_type: 'classic',
      created_at: '2024-10-01T00:00:00Z',
      age_days: 150,
      signal_type: 'stale_90d',
    },
  ],
  dormant: [],
};

const mockBypassData: { offenders: BypassOffender[] } = {
  offenders: [
    {
      actor: 'risky-dev',
      total_bypasses: 15,
      push_protection_bypasses: 10,
      branch_protection_overrides: 5,
      first_bypass_at: '2025-01-01T00:00:00Z',
      last_bypass_at: '2025-03-15T00:00:00Z',
      active_days: 14,
    },
    {
      actor: 'occasional-bypasser',
      total_bypasses: 3,
      push_protection_bypasses: 2,
      branch_protection_overrides: 1,
      first_bypass_at: '2025-02-10T00:00:00Z',
      last_bypass_at: '2025-03-01T00:00:00Z',
      active_days: 5,
    },
  ],
};

const mockCollabData: ExternalCollabResponse = {
  summary: {
    total_active: 5,
    org_level_count: 1,
    elevated_count: 2,
    dormant_count: 1,
  },
  collaborators: [
    {
      github_login: 'old-vendor',
      org: 'acme-corp',
      repo: 'legacy-payments',
      role: 'write',
      granted_at: '2024-01-04T00:00:00Z',
      granted_by: 'admin',
      last_event_at: '2024-10-01T00:00:00Z',
      days_since_last_event: 163,
    },
    {
      github_login: 'auditor-firm',
      org: 'acme-corp',
      repo: 'infra-deploy',
      role: 'admin',
      granted_at: '2026-02-10T00:00:00Z',
      granted_by: null,
      last_event_at: '2026-01-15T00:00:00Z',
      days_since_last_event: 45,
    },
  ],
};

const mockDormantData: { dormant: DormantCollaborator[] } = {
  dormant: [
    {
      github_login: 'contractor-exit1',
      org: 'acme-corp',
      repo: null,
      role: 'member',
      granted_at: '2024-06-01T00:00:00Z',
      last_event_at: '2025-11-03T00:00:00Z',
      days_inactive: 144,
    },
    {
      github_login: 'former-intern',
      org: 'globex',
      repo: null,
      role: 'member',
      granted_at: '2024-03-01T00:00:00Z',
      last_event_at: '2025-09-01T00:00:00Z',
      days_inactive: 207,
    },
    {
      github_login: 'old-vendor',
      org: 'acme-corp',
      repo: 'legacy-payments',
      role: 'outside_collaborator',
      granted_at: '2024-01-04T00:00:00Z',
      last_event_at: '2025-10-14T00:00:00Z',
      days_inactive: 163,
    },
    {
      github_login: 'legacy-bot',
      org: 'acme-corp',
      repo: null,
      role: 'member',
      granted_at: '2024-01-01T00:00:00Z',
      last_event_at: '2025-12-20T00:00:00Z',
      days_inactive: 70,
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
      <AccessIdentityPane />
    </QueryClientProvider>,
  );
}

describe('AccessIdentityPane', () => {
  beforeEach(() => {
    queryResults = {
      'health/pat-health': { data: mockPatData, isLoading: false, isError: false, refetch: vi.fn() },
      'health/bypass-offenders': { data: mockBypassData, isLoading: false, isError: false, refetch: vi.fn() },
      'health/external-collaborators': { data: mockCollabData, isLoading: false, isError: false, refetch: vi.fn() },
      'health/dormant-collaborators': { data: mockDormantData, isLoading: false, isError: false, refetch: vi.fn() },
    };
  });

  it('renders loading spinner when any query is loading', () => {
    queryResults['health/pat-health'] = { data: undefined, isLoading: true, isError: false, refetch: vi.fn() };
    renderPane();
    expect(document.querySelector('[class*="spinner"]')).toBeTruthy();
  });

  it('renders error banner when any query fails', () => {
    queryResults['health/bypass-offenders'] = { data: undefined, isLoading: false, isError: true, refetch: vi.fn() };
    renderPane();
    expect(screen.getByText('Failed to load access & identity data')).toBeInTheDocument();
  });

  it('renders the sample data banner', () => {
    renderPane();
    expect(
      screen.getByText(/Member activity metrics are derived from audit log/),
    ).toBeInTheDocument();
  });

  /* ---- Member activity overview ---- */

  it('renders member activity overview card', () => {
    renderPane();
    expect(screen.getByText('Member activity overview')).toBeInTheDocument();
  });

  it('shows dormant member count from dormant collaborators', () => {
    renderPane();
    // 3 members with >= 90 days inactive
    expect(screen.getByText(/3 members/)).toBeInTheDocument();
    expect(screen.getByText(/no activity in 90\+ days/)).toBeInTheDocument();
  });

  /* ---- PAT health snapshot ---- */

  it('renders PAT health snapshot card', () => {
    renderPane();
    expect(screen.getByText('PAT health snapshot')).toBeInTheDocument();
  });

  it('shows no-expiry token count', () => {
    renderPane();
    expect(screen.getByText(/24 tokens/)).toBeInTheDocument();
    expect(screen.getByText(/with no expiration date/)).toBeInTheDocument();
  });

  it('shows expiring-soon token count', () => {
    renderPane();
    expect(screen.getByText(/12 tokens/)).toBeInTheDocument();
    expect(screen.getByText(/expire within 30 days/)).toBeInTheDocument();
  });

  it('shows stale token count', () => {
    renderPane();
    expect(screen.getByText(/7 tokens/)).toBeInTheDocument();
    expect(screen.getByText(/not used in 90\+ days/)).toBeInTheDocument();
  });

  /* ---- Bypass offenders ---- */

  it('renders bypass offenders section', () => {
    renderPane();
    expect(screen.getByText('Bypass repeat offenders')).toBeInTheDocument();
  });

  it('renders bypass offender actors', () => {
    renderPane();
    expect(screen.getByText('@risky-dev')).toBeInTheDocument();
    expect(screen.getByText('@occasional-bypasser')).toBeInTheDocument();
  });

  it('renders bypass counts with appropriate labels', () => {
    renderPane();
    // risky-dev has 15 bypasses (> 10 → danger label)
    expect(screen.getByText('15')).toBeInTheDocument();
    // occasional-bypasser has 3 bypasses (< 5 → muted label)
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  /* ---- External collaborators ---- */

  it('renders external collaborators section', () => {
    renderPane();
    expect(
      screen.getByText(/Outside collaborators with write\/admin access/),
    ).toBeInTheDocument();
  });

  it('renders collaborator logins', () => {
    renderPane();
    // old-vendor appears in both dormant and external tables
    const oldVendors = screen.getAllByText('@old-vendor');
    expect(oldVendors.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('@auditor-firm')).toBeInTheDocument();
  });

  it('renders risk badges for collaborators', () => {
    renderPane();
    // old-vendor: 163 days, should be "stale & dormant"
    expect(screen.getByText('stale & dormant')).toBeInTheDocument();
    // auditor-firm: admin role with 45 days, should be "admin, review required"
    expect(screen.getByText('admin, review required')).toBeInTheDocument();
  });

  /* ---- Dormant members ---- */

  it('renders dormant members section', () => {
    renderPane();
    expect(screen.getByText('Dormant members (90+ days inactive)')).toBeInTheDocument();
  });

  it('renders dormant member logins', () => {
    renderPane();
    expect(screen.getByText('@contractor-exit1')).toBeInTheDocument();
    expect(screen.getByText('@former-intern')).toBeInTheDocument();
  });

  it('renders days inactive labels', () => {
    renderPane();
    expect(screen.getByText('207 days')).toBeInTheDocument();
    expect(screen.getByText('144 days')).toBeInTheDocument();
    expect(screen.getByText('163 days')).toBeInTheDocument();
  });

  it('shows outside collaborator role label', () => {
    renderPane();
    expect(screen.getByText('outside collaborator')).toBeInTheDocument();
  });

  it('sorts dormant members by days inactive descending', () => {
    renderPane();
    const rows = screen.getAllByText(/@(former-intern|contractor-exit1|old-vendor|legacy-bot)/);
    // former-intern (207) should come first, then old-vendor (163), contractor-exit1 (144), legacy-bot (70)
    expect(rows[0].textContent).toBe('@former-intern');
  });

  /* ---- Token age distribution ---- */

  it('renders token age distribution section', () => {
    renderPane();
    expect(screen.getByText('Token age distribution')).toBeInTheDocument();
  });

  it('renders the chart for token age', () => {
    renderPane();
    const charts = screen.getAllByTestId('echarts-mock');
    expect(charts.length).toBeGreaterThanOrEqual(1);
  });

  /* ---- Empty states ---- */

  it('renders empty state for bypass offenders', () => {
    queryResults['health/bypass-offenders'] = {
      data: { offenders: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    expect(screen.getByText('No bypass offenders found')).toBeInTheDocument();
  });

  it('renders empty state for external collaborators', () => {
    queryResults['health/external-collaborators'] = {
      data: {
        summary: { total_active: 0, org_level_count: 0, elevated_count: 0, dormant_count: 0 },
        collaborators: [],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    expect(screen.getByText('No external collaborators found')).toBeInTheDocument();
  });

  it('renders empty state for dormant members', () => {
    queryResults['health/dormant-collaborators'] = {
      data: { dormant: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    expect(screen.getByText('No dormant members found')).toBeInTheDocument();
  });

  it('renders singular text for single token counts', () => {
    queryResults['health/pat-health'] = {
      data: {
        summary: { no_expiry_count: 1, expired_count: 1, stale_90d_count: 1 },
        tokens: [
          {
            github_login: 'user1',
            token_name: 'tok',
            token_id: 't1',
            token_type: 'classic',
            created_at: '2024-01-01T00:00:00Z',
            age_days: 10,
            signal_type: 'no_expiry',
          },
        ],
        dormant: [],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    renderPane();
    const tokenTexts = screen.getAllByText(/1 token\b/);
    expect(tokenTexts.length).toBe(3);
  });

  /* ---- Member activity drill-down ---- */

  it('opens dormant member drill-down when dormant count is clicked', () => {
    renderPane();
    const dormantStat = screen.getByRole('button', {
      name: /dormant members.*click to view/i,
    });
    fireEvent.click(dormantStat);
    // Modal opened — close button appears
    expect(screen.getByLabelText('Close')).toBeInTheDocument();
    // Title appears twice: once in DormantMembersTable section, once in the modal
    const titles = screen.getAllByText('Dormant members (90+ days inactive)');
    expect(titles.length).toBe(2);
  });

  it('shows dormant members in drill-down modal', () => {
    renderPane();
    const dormantStat = screen.getByRole('button', {
      name: /dormant members.*click to view/i,
    });
    fireEvent.click(dormantStat);
    // Should show column headers from the DataTable in the modal
    const memberHeaders = screen.getAllByText('Member');
    expect(memberHeaders.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Days Inactive')).toBeInTheDocument();
  });

  it('opens at-risk member drill-down when at-risk count is clicked', () => {
    renderPane();
    const atRiskStat = screen.getByRole('button', {
      name: /at-risk members.*click to view/i,
    });
    fireEvent.click(atRiskStat);
    expect(screen.getByText('At-risk members (60–90 days inactive)')).toBeInTheDocument();
  });

  it('opens new member drill-down when new count is clicked', () => {
    renderPane();
    const newStat = screen.getByRole('button', {
      name: /new members.*click to view/i,
    });
    fireEvent.click(newStat);
    expect(screen.getByText('New members (joined in last 30 days)')).toBeInTheDocument();
  });

  /* ---- PAT health drill-down ---- */

  it('opens no-expiry token drill-down when no-expiry count is clicked', () => {
    renderPane();
    const noExpiryStat = screen.getByRole('button', {
      name: /tokens with no expiry.*click to view/i,
    });
    fireEvent.click(noExpiryStat);
    expect(screen.getByText('Tokens with no expiration date')).toBeInTheDocument();
  });

  it('shows token data in no-expiry drill-down modal', () => {
    renderPane();
    const noExpiryStat = screen.getByRole('button', {
      name: /tokens with no expiry/i,
    });
    fireEvent.click(noExpiryStat);
    // Should show the no_expiry token (user1)
    expect(screen.getByText('User')).toBeInTheDocument();
    expect(screen.getByText('Token Name')).toBeInTheDocument();
    expect(screen.getByText('Age (days)')).toBeInTheDocument();
  });

  it('opens expiring token drill-down when expiring count is clicked', () => {
    renderPane();
    const expiringStat = screen.getByRole('button', {
      name: /tokens expiring soon.*click to view/i,
    });
    fireEvent.click(expiringStat);
    expect(screen.getByText('Tokens expiring within 30 days')).toBeInTheDocument();
  });

  it('opens stale token drill-down when stale count is clicked', () => {
    renderPane();
    const staleStat = screen.getByRole('button', {
      name: /stale tokens.*click to view/i,
    });
    fireEvent.click(staleStat);
    expect(screen.getByText('Stale tokens (unused 90+ days)')).toBeInTheDocument();
  });

  it('closes member drill-down modal when close button is clicked', () => {
    renderPane();
    const dormantStat = screen.getByRole('button', {
      name: /dormant members/i,
    });
    fireEvent.click(dormantStat);
    const closeBtn = screen.getByLabelText('Close');
    fireEvent.click(closeBtn);
    expect(screen.queryByLabelText('Close')).not.toBeInTheDocument();
  });

  it('member drill-down stat is keyboard accessible', () => {
    renderPane();
    const dormantStat = screen.getByRole('button', {
      name: /dormant members/i,
    });
    fireEvent.keyDown(dormantStat, { key: 'Enter' });
    expect(screen.getByLabelText('Close')).toBeInTheDocument();
  });
});
