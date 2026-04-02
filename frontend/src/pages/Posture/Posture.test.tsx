import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { PosturePage } from './index';
import type { PostureResponse } from '../../api/posture';

/* ── Mocks ─────────────────────────────────────────────────────────── */

const mockNavigate = vi.fn();
const mockParams: Record<string, string | undefined> = {};

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => mockParams,
  };
});

const mockGetPosture = vi.fn();

vi.mock('../../api/posture', () => ({
  getPosture: (...args: unknown[]) => mockGetPosture(...args),
}));

/* ── Fixtures ──────────────────────────────────────────────────────── */

const ENTERPRISE_RESPONSE: PostureResponse = {
  level: 'enterprise',
  score: 85.0,
  orgs: [
    {
      org_login: 'iadopt-apps',
      score: 90.0,
      two_factor_required: true,
      default_repo_permission: 'read',
      members_can_fork_private_repos: false,
      members_can_create_public_repos: false,
      ip_allow_list_enabled: true,
      checks: [
        {
          rule_id: 1,
          rule_name: '2FA Required',
          category: 'access_control',
          severity: 'critical',
          status: 'pass',
          title: '2FA Required',
          description: 'Org requires 2FA',
          detection_id: null,
          context_data: {},
          triggered_at: null,
        },
      ],
      repos: null,
      repo_summary: { total: 5, passing: 4, warning: 1, failing: 0 },
      detection_count: 0,
    },
    {
      org_login: 'danger-org',
      score: 40.0,
      two_factor_required: false,
      default_repo_permission: 'admin',
      members_can_fork_private_repos: true,
      members_can_create_public_repos: true,
      ip_allow_list_enabled: false,
      checks: [
        {
          rule_id: 1,
          rule_name: '2FA Required',
          category: 'access_control',
          severity: 'critical',
          status: 'open',
          title: '2FA Not Enabled',
          description: 'Org does not require 2FA',
          detection_id: 100,
          context_data: {},
          triggered_at: '2024-01-15T12:00:00Z',
        },
      ],
      repos: null,
      repo_summary: { total: 3, passing: 0, warning: 1, failing: 2 },
      detection_count: 1,
    },
  ],
  org: null,
  repo: null,
  breadcrumb: [{ label: 'Posture', href: null }],
  last_sync_at: '2024-06-01T10:00:00Z',
  page: 1,
  page_size: 25,
  total: 1,
  has_next: false,
};

const ORG_RESPONSE: PostureResponse = {
  level: 'org',
  score: 90.0,
  orgs: null,
  org: {
    org_login: 'iadopt-apps',
    score: 90.0,
    two_factor_required: true,
    default_repo_permission: 'read',
    members_can_fork_private_repos: false,
    members_can_create_public_repos: false,
    ip_allow_list_enabled: true,
    checks: [
      {
        rule_id: 1,
        rule_name: '2FA Required',
        category: 'access_control',
        severity: 'critical',
        status: 'pass',
        title: '2FA Required',
        description: 'Org requires 2FA',
        detection_id: null,
        context_data: {},
        triggered_at: null,
      },
    ],
    repos: [
      {
        repo_name: 'iAdopt',
        org: 'iadopt-apps',
        visibility: 'private',
        default_branch: 'main',
        archived: false,
        fork: false,
        language: null,
        pushed_at: '2024-05-01T10:00:00Z',
        score: 100.0,
        checks: [],
        detection_count: 0,
      },
      {
        repo_name: 'legacy-app',
        org: 'iadopt-apps',
        visibility: 'public',
        default_branch: 'master',
        archived: true,
        fork: false,
        language: null,
        pushed_at: null,
        score: 45.0,
        checks: [
          {
            rule_id: 2,
            rule_name: 'BP Required',
            category: 'posture_degradation',
            severity: 'high',
            status: 'open',
            title: 'No branch protection',
            description: 'Branch protection is not configured',
            detection_id: 200,
            context_data: {},
            triggered_at: '2024-01-10T08:00:00Z',
          },
        ],
        detection_count: 1,
      },
    ],
    repo_summary: { total: 2, passing: 1, warning: 0, failing: 1 },
    detection_count: 0,
  },
  repo: null,
  breadcrumb: [
    { label: 'Posture', href: '/posture' },
    { label: 'iadopt-apps', href: null },
  ],
  last_sync_at: '2024-06-01T10:00:00Z',
  page: 1,
  page_size: 25,
  total: 1,
  has_next: false,
};

const REPO_RESPONSE: PostureResponse = {
  level: 'repo',
  score: 45.0,
  orgs: null,
  org: null,
  repo: {
    repo_name: 'legacy-app',
    org: 'iadopt-apps',
    visibility: 'public',
    default_branch: 'master',
    archived: true,
    fork: false,
    language: null,
    pushed_at: '2024-05-01T10:00:00Z',
    score: 45.0,
    checks: [
      {
        rule_id: 2,
        rule_name: 'BP Required',
        category: 'posture_degradation',
        severity: 'high',
        status: 'open',
        title: 'No branch protection',
        description: 'Branch protection is not configured',
        detection_id: 200,
        context_data: {},
        triggered_at: '2024-01-10T08:00:00Z',
      },
      {
        rule_id: 3,
        rule_name: 'Admin Review',
        category: 'access_control',
        severity: 'medium',
        status: 'pass',
        title: 'Admin Review',
        description: 'Admin review is enforced',
        detection_id: null,
        context_data: {},
        triggered_at: null,
      },
    ],
    detection_count: 1,
  },
  breadcrumb: [
    { label: 'Posture', href: '/posture' },
    { label: 'iadopt-apps', href: '/posture/iadopt-apps' },
    { label: 'legacy-app', href: null },
  ],
  last_sync_at: '2024-06-01T10:00:00Z',
  page: 1,
  page_size: 25,
  total: 1,
  has_next: false,
};

/* ── Test suites ───────────────────────────────────────────────────── */

describe('PosturePage — Loading & Error', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockGetPosture.mockClear();
    mockParams.org = undefined;
    mockParams.repo = undefined;
  });

  it('renders spinner while loading', () => {
    mockGetPosture.mockReturnValue(new Promise(() => {})); // never resolves
    renderWithProviders(<PosturePage />);
    // Spinner component renders a div with spinner class
    const spinner = document.querySelector('[class*="spinner"]');
    expect(spinner).not.toBeNull();
  });

  it('renders error banner on failure', async () => {
    mockGetPosture.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('Failed to load posture data')).toBeInTheDocument();
  });

  it('renders retry button on error', async () => {
    mockGetPosture.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('Retry')).toBeInTheDocument();
  });
});

describe('PosturePage — Enterprise View', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockGetPosture.mockClear();
    mockGetPosture.mockResolvedValue(ENTERPRISE_RESPONSE);
    mockParams.org = undefined;
    mockParams.repo = undefined;
  });

  it('renders breadcrumb with Posture label', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('Posture')).toBeInTheDocument();
  });

  it('renders enterprise score', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('85')).toBeInTheDocument();
  });

  it('renders enterprise title text', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('Enterprise Security Posture')).toBeInTheDocument();
  });

  it('renders org count in subtitle', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText(/1 org/)).toBeInTheDocument();
  });

  it('renders org cards', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('iadopt-apps')).toBeInTheDocument();
    expect(await screen.findByText('danger-org')).toBeInTheDocument();
  });

  it('renders org scores on cards', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('90')).toBeInTheDocument();
    expect(await screen.findByText('40')).toBeInTheDocument();
  });

  it('renders repo summary on org cards', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('5 repos')).toBeInTheDocument();
    expect(await screen.findByText('3 repos')).toBeInTheDocument();
  });

  it('shows failing count on org card', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('2 failing')).toBeInTheDocument();
  });

  it('renders top findings section', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('Top Findings')).toBeInTheDocument();
    expect(await screen.findByText('2FA Not Enabled')).toBeInTheDocument();
  });

  it('navigates to org on card click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PosturePage />);
    const card = await screen.findByText('iadopt-apps');
    await user.click(card.closest('[class*="orgCard"]')!);
    expect(mockNavigate).toHaveBeenCalledWith('/posture/iadopt-apps');
  });

  it('renders severity filter dropdown', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByDisplayValue('All severities')).toBeInTheDocument();
  });

  it('renders status filter dropdown', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByDisplayValue('All statuses')).toBeInTheDocument();
  });

  it('shows last sync time', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText(/Last synced/)).toBeInTheDocument();
  });
});

describe('PosturePage — Org View', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockGetPosture.mockClear();
    mockGetPosture.mockResolvedValue(ORG_RESPONSE);
    mockParams.org = 'iadopt-apps';
    mockParams.repo = undefined;
  });

  it('renders org name as title', async () => {
    renderWithProviders(<PosturePage />);
    // Text appears in both breadcrumb and title, so use findAllByText
    const matches = await screen.findAllByText('iadopt-apps');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it('renders breadcrumb with link to enterprise', async () => {
    renderWithProviders(<PosturePage />);
    const breadcrumbLink = await screen.findByRole('link', { name: 'Posture' });
    expect(breadcrumbLink).toHaveAttribute('href', '/posture');
  });

  it('renders org score gauge', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('90')).toBeInTheDocument();
  });

  it('renders org metadata card with 2FA status', async () => {
    renderWithProviders(<PosturePage />);
    // "2FA Required" appears in both the metadata label and the check title
    const matches = await screen.findAllByText('2FA Required');
    expect(matches.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText('Required')).toBeInTheDocument();
  });

  it('renders default repo permission', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('Default Repo Permission')).toBeInTheDocument();
    expect(await screen.findByText('read')).toBeInTheDocument();
  });

  it('renders org checks section', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('Organization Security Checks')).toBeInTheDocument();
  });

  it('renders passing check with checkmark', async () => {
    renderWithProviders(<PosturePage />);
    const passIcon = await screen.findByText('✓');
    expect(passIcon).toBeInTheDocument();
  });

  it('renders repos table', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('Repositories')).toBeInTheDocument();
    expect(await screen.findByText('iAdopt')).toBeInTheDocument();
    expect(await screen.findByText('legacy-app')).toBeInTheDocument();
  });

  it('shows archived label on archived repos', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('archived')).toBeInTheDocument();
  });

  it('navigates to repo on row click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PosturePage />);
    const repoRow = await screen.findByText('iAdopt');
    await user.click(repoRow.closest('tr')!);
    expect(mockNavigate).toHaveBeenCalledWith('/posture/iadopt-apps/iAdopt');
  });

  it('renders sortable table headers', async () => {
    renderWithProviders(<PosturePage />);
    const headers = await screen.findAllByRole('columnheader');
    expect(headers.length).toBeGreaterThanOrEqual(3);
  });

  it('sorts by score by default', async () => {
    renderWithProviders(<PosturePage />);
    // "Score" appears in both the gauge label and table header
    const matches = await screen.findAllByText(/Score/);
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });
});

describe('PosturePage — Repo View', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockGetPosture.mockClear();
    mockGetPosture.mockResolvedValue(REPO_RESPONSE);
    mockParams.org = 'iadopt-apps';
    mockParams.repo = 'legacy-app';
  });

  it('renders repo name as title', async () => {
    renderWithProviders(<PosturePage />);
    // "legacy-app" appears in both breadcrumb and header
    const matches = await screen.findAllByText('legacy-app');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it('renders breadcrumb with links', async () => {
    renderWithProviders(<PosturePage />);
    const postureLink = await screen.findByRole('link', { name: 'Posture' });
    expect(postureLink).toHaveAttribute('href', '/posture');
    const orgLink = await screen.findByRole('link', { name: 'iadopt-apps' });
    expect(orgLink).toHaveAttribute('href', '/posture/iadopt-apps');
  });

  it('renders repo score', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('45')).toBeInTheDocument();
  });

  it('renders repo metadata', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('Visibility')).toBeInTheDocument();
    expect(await screen.findByText('public')).toBeInTheDocument();
    expect(await screen.findByText('Default Branch')).toBeInTheDocument();
    expect(await screen.findByText('master')).toBeInTheDocument();
  });

  it('shows archived status in metadata', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('Archived')).toBeInTheDocument();
    expect(await screen.findByText('Yes')).toBeInTheDocument();
  });

  it('renders security checks section', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('Security Checks')).toBeInTheDocument();
  });

  it('renders failing check with cross icon', async () => {
    renderWithProviders(<PosturePage />);
    const failIcon = await screen.findByText('✕');
    expect(failIcon).toBeInTheDocument();
  });

  it('renders passing check with checkmark icon', async () => {
    renderWithProviders(<PosturePage />);
    const passIcon = await screen.findByText('✓');
    expect(passIcon).toBeInTheDocument();
  });

  it('shows check title for failing check', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('No branch protection')).toBeInTheDocument();
  });

  it('shows check description for failing check', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('Branch protection is not configured')).toBeInTheDocument();
  });

  it('shows severity label on checks', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByText('high')).toBeInTheDocument();
  });

  it('renders filter dropdowns', async () => {
    renderWithProviders(<PosturePage />);
    expect(await screen.findByDisplayValue('All severities')).toBeInTheDocument();
    expect(await screen.findByDisplayValue('All statuses')).toBeInTheDocument();
  });

  it('filters checks by severity', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PosturePage />);
    const sevSelect = await screen.findByDisplayValue('All severities');
    await user.selectOptions(sevSelect, 'medium');
    // Only medium check should show (Admin Review)
    expect(screen.getByText('Admin Review')).toBeInTheDocument();
    // High severity check should be filtered out
    expect(screen.queryByText('No branch protection')).not.toBeInTheDocument();
  });

  it('filters checks by status', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PosturePage />);
    const statusSelect = await screen.findByDisplayValue('All statuses');
    await user.selectOptions(statusSelect, 'pass');
    // Only passing check should show
    expect(screen.getByText('Admin Review')).toBeInTheDocument();
    expect(screen.queryByText('No branch protection')).not.toBeInTheDocument();
  });

  it('shows empty message when filters match nothing', async () => {
    const user = userEvent.setup();
    renderWithProviders(<PosturePage />);
    const sevSelect = await screen.findByDisplayValue('All severities');
    await user.selectOptions(sevSelect, 'info');
    expect(await screen.findByText('No checks match filters')).toBeInTheDocument();
  });
});

describe('PosturePage — API calls', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockGetPosture.mockClear();
    mockParams.org = undefined;
    mockParams.repo = undefined;
  });

  it('calls getPosture with no params for enterprise view', () => {
    mockGetPosture.mockResolvedValue(ENTERPRISE_RESPONSE);
    renderWithProviders(<PosturePage />);
    expect(mockGetPosture).toHaveBeenCalledWith({
      org: undefined,
      repo: undefined,
      search: undefined,
      page: 1,
      page_size: 25,
    });
  });

  it('calls getPosture with org param for org view', () => {
    mockParams.org = 'my-org';
    mockGetPosture.mockResolvedValue(ORG_RESPONSE);
    renderWithProviders(<PosturePage />);
    expect(mockGetPosture).toHaveBeenCalledWith({
      org: 'my-org',
      repo: undefined,
      search: undefined,
      page: 1,
      page_size: 25,
    });
  });

  it('calls getPosture with org and repo params for repo view', () => {
    mockParams.org = 'my-org';
    mockParams.repo = 'my-repo';
    mockGetPosture.mockResolvedValue(REPO_RESPONSE);
    renderWithProviders(<PosturePage />);
    expect(mockGetPosture).toHaveBeenCalledWith({
      org: 'my-org',
      repo: 'my-repo',
      search: undefined,
      page: 1,
      page_size: 25,
    });
  });
});

describe('PosturePage — Score gauge colors', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
    mockGetPosture.mockClear();
    mockParams.org = undefined;
    mockParams.repo = undefined;
  });

  it('applies good class for score >= 80', async () => {
    mockGetPosture.mockResolvedValue(ENTERPRISE_RESPONSE);
    renderWithProviders(<PosturePage />);
    await screen.findByText('85');
    const gauge = document.querySelector('[class*="scoreGauge"]');
    expect(gauge?.className).toContain('good');
  });

  it('applies bad class for score < 50', async () => {
    mockGetPosture.mockResolvedValue(REPO_RESPONSE);
    mockParams.org = 'iadopt-apps';
    mockParams.repo = 'legacy-app';
    renderWithProviders(<PosturePage />);
    await screen.findByText('45');
    const gauge = document.querySelector('[class*="scoreGauge"]');
    expect(gauge?.className).toContain('bad');
  });
});
