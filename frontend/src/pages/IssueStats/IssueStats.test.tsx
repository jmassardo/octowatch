import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { IssueStatsPage } from './index';

/* ── Mocks ─────────────────────────────────────────────────────────── */

const mockGetByOrg = vi.fn();
const mockGetByRepo = vi.fn();

vi.mock('../../api/issueStats', () => ({
  getIssueStatsByOrg: (...args: unknown[]) => mockGetByOrg(...args),
  getIssueStatsByRepo: (...args: unknown[]) => mockGetByRepo(...args),
}));

/* ── Fixtures ──────────────────────────────────────────────────────── */

const BY_ORG_RESPONSE = {
  window_days: 30,
  total_opened: 35,
  total_closed: 30,
  orgs: [
    {
      org: 'acme-corp',
      opened: 25,
      closed: 18,
      net_open: 7,
      avg_hours_to_close: 48.5,
    },
    {
      org: 'beta-org',
      opened: 10,
      closed: 12,
      net_open: -2,
      avg_hours_to_close: 24.0,
    },
  ],
};

const BY_REPO_RESPONSE = {
  window_days: 30,
  total_opened: 35,
  total_closed: 30,
  repos: [
    {
      org: 'acme-corp',
      repo: 'acme-corp/api',
      opened: 15,
      closed: 10,
      net_open: 5,
      avg_hours_to_close: 36.2,
    },
    {
      org: 'acme-corp',
      repo: 'acme-corp/web',
      opened: 10,
      closed: 8,
      net_open: 2,
      avg_hours_to_close: 72.0,
    },
  ],
};

/* ── Tests ─────────────────────────────────────────────────────────── */

describe('IssueStatsPage — By Organization Tab', () => {
  beforeEach(() => {
    mockGetByOrg.mockClear();
    mockGetByRepo.mockClear();
    mockGetByOrg.mockResolvedValue(BY_ORG_RESPONSE);
    mockGetByRepo.mockResolvedValue(BY_REPO_RESPONSE);
  });

  it('renders page title', async () => {
    renderWithProviders(<IssueStatsPage />);
    expect(await screen.findByText('Issue Stats')).toBeInTheDocument();
  });

  it('renders page description', async () => {
    renderWithProviders(<IssueStatsPage />);
    expect(
      await screen.findByText('Issue activity metrics grouped by organization and repository.'),
    ).toBeInTheDocument();
  });

  it('renders summary metric cards', async () => {
    renderWithProviders(<IssueStatsPage />);
    expect(await screen.findByText('Issues Opened')).toBeInTheDocument();
    expect(await screen.findByText('Issues Closed')).toBeInTheDocument();
    expect(await screen.findByText('Organizations')).toBeInTheDocument();
    // "Net Open" appears as both a MetricCard label and table header, so check for multiple
    const netOpenElements = await screen.findAllByText('Net Open');
    expect(netOpenElements.length).toBeGreaterThanOrEqual(1);
  });

  it('renders summary values from API', async () => {
    renderWithProviders(<IssueStatsPage />);
    expect(await screen.findByText('35')).toBeInTheDocument();
    expect(await screen.findByText('30')).toBeInTheDocument();
  });

  it('renders org data in table', async () => {
    renderWithProviders(<IssueStatsPage />);
    expect(await screen.findByText('acme-corp')).toBeInTheDocument();
    expect(await screen.findByText('beta-org')).toBeInTheDocument();
  });

  it('shows time window selector', async () => {
    renderWithProviders(<IssueStatsPage />);
    const select = await screen.findByLabelText('Time window');
    expect(select).toBeInTheDocument();
  });

  it('renders By Organization tab as active by default', async () => {
    renderWithProviders(<IssueStatsPage />);
    // The tab button contains "By Organization" text
    const tabs = await screen.findAllByText('By Organization');
    expect(tabs.length).toBeGreaterThanOrEqual(1);
  });

  it('renders empty state when no orgs', async () => {
    mockGetByOrg.mockResolvedValue({
      window_days: 30,
      total_opened: 0,
      total_closed: 0,
      orgs: [],
    });
    renderWithProviders(<IssueStatsPage />);
    expect(
      await screen.findByText('No issue data found in the selected time window'),
    ).toBeInTheDocument();
  });
});

describe('IssueStatsPage — By Repository Tab', () => {
  beforeEach(() => {
    mockGetByOrg.mockClear();
    mockGetByRepo.mockClear();
    mockGetByOrg.mockResolvedValue(BY_ORG_RESPONSE);
    mockGetByRepo.mockResolvedValue(BY_REPO_RESPONSE);
  });

  it('switches to By Repository tab', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IssueStatsPage />);
    const repoTab = await screen.findByText('By Repository', { exact: false });
    await user.click(repoTab);
    expect(await screen.findByText('acme-corp/api')).toBeInTheDocument();
    expect(await screen.findByText('acme-corp/web')).toBeInTheDocument();
  });

  it('shows repo table columns', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IssueStatsPage />);
    await user.click(await screen.findByText('By Repository', { exact: false }));
    expect(await screen.findByText('Repository')).toBeInTheDocument();
  });
});

describe('IssueStatsPage — Error Handling', () => {
  beforeEach(() => {
    mockGetByOrg.mockClear();
    mockGetByRepo.mockClear();
  });

  it('shows error banner on org fetch failure', async () => {
    mockGetByOrg.mockRejectedValue(new Error('Network error'));
    renderWithProviders(<IssueStatsPage />);
    expect(
      await screen.findByText('Failed to load issue stats by org'),
    ).toBeInTheDocument();
  });
});
