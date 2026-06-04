import { describe, it, expect, vi } from 'vitest';
import { screen, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { DevActivityPage } from './index';

vi.mock('echarts-for-react', () => ({
  default: () => null,
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useParams: () => ({ tab: 'activity' }),
  };
});

// ---------------------------------------------------------------------------
// Mock helpers (vi.hoisted so they're available inside vi.mock factories)
// ---------------------------------------------------------------------------

const { mockDevelopers } = vi.hoisted(() => {
  const mockDevelopers = [
    {
      login: 'alice',
      event_count: 10,
      pr_count: 10,
      review_count: 0,
      top_repos: ['repo-a'],
      repo_count: 1,
      last_active: new Date(Date.now() - 86_400_000).toISOString(),
      weekly_counts: [0, 0, 2, 2, 2, 2, 2],
    },
    {
      login: 'bob',
      event_count: 3,
      pr_count: 3,
      review_count: 0,
      top_repos: ['repo-b'],
      repo_count: 1,
      last_active: new Date(Date.now() - 2 * 86_400_000).toISOString(),
      weekly_counts: [0, 0, 1, 1, 1, 0, 0],
    },
    {
      login: 'carol',
      event_count: 2,
      pr_count: 2,
      review_count: 0,
      top_repos: ['repo-c'],
      repo_count: 1,
      last_active: new Date(Date.now() - 3 * 86_400_000).toISOString(),
      weekly_counts: [0, 0, 1, 1, 0, 0, 0],
    },
    {
      login: 'dave',
      event_count: 2,
      pr_count: 0,
      review_count: 0,
      top_repos: ['repo-d'],
      repo_count: 1,
      last_active: new Date(Date.now() - 4 * 86_400_000).toISOString(),
      weekly_counts: [0, 0, 0, 1, 1, 0, 0],
    },
    {
      login: 'eve',
      event_count: 1,
      pr_count: 0,
      review_count: 0,
      top_repos: ['repo-e'],
      repo_count: 1,
      last_active: new Date(Date.now() - 5 * 86_400_000).toISOString(),
      weekly_counts: [0, 0, 0, 0, 1, 0, 0],
    },
    {
      login: 'frank',
      event_count: 1,
      pr_count: 0,
      review_count: 0,
      top_repos: ['repo-f'],
      repo_count: 1,
      last_active: new Date(Date.now() - 6 * 86_400_000).toISOString(),
      weekly_counts: [0, 0, 0, 0, 0, 1, 0],
    },
  ];

  return { mockDevelopers };
});

// ---------------------------------------------------------------------------
// Mock API modules
// ---------------------------------------------------------------------------

vi.mock('../../api/detections', () => ({
  listDetections: vi.fn().mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 200,
  }),
}));

vi.mock('../../api/healthSignals', () => ({
  getTeams: vi.fn().mockResolvedValue({ teams: [] }),
}));

vi.mock('../../api/devActivity', () => ({
  getDevelopers: vi.fn().mockResolvedValue({
    developers: mockDevelopers,
    lookback_days: 90,
  }),
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DevActivityPage', () => {
  it('renders page title and subtitle', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('Developer Activity')).toBeInTheDocument();
    expect(
      screen.getByText('Track developer engagement and contribution patterns'),
    ).toBeInTheDocument();
  });

  it('renders empty team note when no teams available', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('No team data available')).toBeInTheDocument();
  });

  it('renders searchable team filter dropdown when teams are available', async () => {
    const { getTeams } = await import('../../api/healthSignals');
    vi.mocked(getTeams).mockResolvedValueOnce({
      teams: [
        {
          org: 'test-org',
          team_slug: 'platform',
          team_name: 'platform-team',
          members: ['alice', 'bob'],
        },
        { org: 'test-org', team_slug: 'backend', team_name: 'backend-team', members: ['carol'] },
      ],
    });

    renderWithProviders(<DevActivityPage />);

    const input = await screen.findByRole('combobox', { name: 'Filter developers by team' });
    expect(input).toBeInTheDocument();
  });

  it('filters suggestions as user types in team autocomplete', async () => {
    const user = userEvent.setup();
    const { getTeams } = await import('../../api/healthSignals');
    vi.mocked(getTeams).mockResolvedValueOnce({
      teams: [
        {
          org: 'test-org',
          team_slug: 'platform',
          team_name: 'platform-team',
          members: ['alice', 'bob'],
        },
        { org: 'test-org', team_slug: 'backend', team_name: 'backend-team', members: ['carol'] },
      ],
    });

    renderWithProviders(<DevActivityPage />);

    const input = await screen.findByRole('combobox', { name: 'Filter developers by team' });
    await user.type(input, 'plat');

    expect(screen.getByRole('option', { name: 'platform-team' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'backend-team' })).not.toBeInTheDocument();
  });

  it('selects team from autocomplete and shows clear button', async () => {
    const user = userEvent.setup();
    const { getTeams } = await import('../../api/healthSignals');
    vi.mocked(getTeams).mockResolvedValueOnce({
      teams: [
        {
          org: 'test-org',
          team_slug: 'platform',
          team_name: 'platform-team',
          members: ['alice', 'bob'],
        },
        { org: 'test-org', team_slug: 'backend', team_name: 'backend-team', members: ['carol'] },
      ],
    });

    renderWithProviders(<DevActivityPage />);

    const input = await screen.findByRole('combobox', { name: 'Filter developers by team' });
    await user.type(input, 'plat');

    const suggestion = screen.getByRole('option', { name: 'platform-team' });
    fireEvent.mouseDown(suggestion);

    expect(screen.getByLabelText('Clear team filter')).toBeInTheDocument();
  });

  it('clears team filter when clear button is clicked', async () => {
    const user = userEvent.setup();
    const { getTeams } = await import('../../api/healthSignals');
    vi.mocked(getTeams).mockResolvedValueOnce({
      teams: [
        {
          org: 'test-org',
          team_slug: 'platform',
          team_name: 'platform-team',
          members: ['alice', 'bob'],
        },
        { org: 'test-org', team_slug: 'backend', team_name: 'backend-team', members: ['carol'] },
      ],
    });

    renderWithProviders(<DevActivityPage />);

    const input = await screen.findByRole('combobox', { name: 'Filter developers by team' });
    await user.type(input, 'plat');

    const suggestion = screen.getByRole('option', { name: 'platform-team' });
    fireEvent.mouseDown(suggestion);

    const clearBtn = screen.getByLabelText('Clear team filter');
    await user.click(clearBtn);

    expect(screen.queryByLabelText('Clear team filter')).not.toBeInTheDocument();
  });

  it('renders Work distribution section title', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText(/Work distribution — last 30 days/)).toBeInTheDocument();
  });

  it('PR authorship bars are clickable with role=button', async () => {
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('PR authorship share');
    await screen.findAllByText(/@alice/);

    const barRows = document.querySelectorAll('.barRow.clickableBar');
    expect(barRows.length).toBeGreaterThanOrEqual(5);

    barRows.forEach((row) => {
      expect(row.getAttribute('role')).toBe('button');
    });
  });

  it('Others row opens modal on click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    const othersRow = await screen.findByText(/others \(/);
    await user.click(othersRow.closest('[role="button"]')!);

    expect(await screen.findByText('Other contributors')).toBeInTheDocument();

    const modalTable = document.querySelector('.othersTable') as HTMLElement;
    expect(within(modalTable).getByText(/@frank/)).toBeInTheDocument();
  });

  it('activity concentration bars are clickable', async () => {
    renderWithProviders(<DevActivityPage />);

    await screen.findAllByText(/@alice/);

    const allClickableBars = document.querySelectorAll('.clickableBar[role="button"]');
    expect(allClickableBars.length).toBeGreaterThanOrEqual(6);
  });

  it('warning text links are clickable when top actor >40%', async () => {
    renderWithProviders(<DevActivityPage />);

    const warningText = await screen.findByText(/accounts for/);
    expect(warningText).toBeInTheDocument();

    const warningContainer = warningText.closest('div')!;
    const clickableElements = warningContainer.querySelectorAll('.clickableText[role="button"]');
    expect(clickableElements.length).toBe(2);

    const actorLink = within(warningContainer).getByText(`@${mockDevelopers[0].login}`);
    expect(actorLink.getAttribute('role')).toBe('button');
  });

  it('renders Top contributors table with developer rows', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('Top contributors')).toBeInTheDocument();
    // Table should have column headers - use getAllByText since "PRs" etc. may appear in multiple places
    const prHeaders = screen.getAllByText('PRs');
    expect(prHeaders.length).toBeGreaterThanOrEqual(1);
    // Verify it has the Trend column which is unique to the new table
    expect(screen.getByText('Trend')).toBeInTheDocument();
    expect(screen.getByText('Last Active')).toBeInTheDocument();
  });

  it('developer detail panel opens on table row click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    // Wait for the contributors table to render
    await screen.findByText('Top contributors');
    // Find all @alice texts — one in work distribution bars, one in table
    const aliceTexts = await screen.findAllByText(/@alice/);
    // The table cell one should be inside a table row with a td
    const tableAlice = aliceTexts.find((el) => el.closest('td'));
    expect(tableAlice).toBeTruthy();
    const row = tableAlice!.closest('tr')!;
    await user.click(row);

    const drawerPanel = await screen.findByTestId('drawer-panel');
    expect(within(drawerPanel).getByText('@alice')).toBeInTheDocument();
  });

  it('developer detail panel opens on Enter key in table row', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Top contributors');
    const bobTexts = await screen.findAllByText(/@bob/);
    const tableBob = bobTexts.find((el) => el.closest('td'));
    expect(tableBob).toBeTruthy();
    const row = tableBob!.closest('tr')!;
    row.focus();
    await user.keyboard('{Enter}');

    const drawerPanel = await screen.findByTestId('drawer-panel');
    expect(within(drawerPanel).getByText('@bob')).toBeInTheDocument();
  });

  it('renders Work breakdown widget', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('Work breakdown')).toBeInTheDocument();
  });

  it('renders Contribution trends widget', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('Contribution trends — weekly')).toBeInTheDocument();
  });

  it('renders Activity distribution widget with buckets', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('Activity distribution')).toBeInTheDocument();
    expect(screen.getByText('Active (≤7d)')).toBeInTheDocument();
    expect(screen.getByText('Moderate (7–30d)')).toBeInTheDocument();
    expect(screen.getByText(/Inactive/)).toBeInTheDocument();
  });

  it('does not render Platform usage section', async () => {
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Developer Activity');
    expect(screen.queryByText(/Platform usage/)).not.toBeInTheDocument();
  });

  it('does not render tab navigation', async () => {
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Developer Activity');
    expect(screen.queryByText('Team Health')).not.toBeInTheDocument();
  });
});
