import { describe, it, expect, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { DevActivityPage } from './index';

// ---------------------------------------------------------------------------
// Mock helpers (vi.hoisted so they're available inside vi.mock factories)
// ---------------------------------------------------------------------------

const { mockDevelopers } = vi.hoisted(() => {
  // alice has ~53% share (10/19) to trigger the >40% warning
  const mockDevelopers = [
    { login: 'alice', event_count: 10, pr_count: 10, review_count: 0, top_repos: ['repo-a'], repo_count: 1, last_active: new Date(Date.now() - 86_400_000).toISOString(), weekly_counts: [0, 0, 2, 2, 2, 2, 2] },
    { login: 'bob', event_count: 3, pr_count: 3, review_count: 0, top_repos: ['repo-b'], repo_count: 1, last_active: new Date(Date.now() - 2 * 86_400_000).toISOString(), weekly_counts: [0, 0, 1, 1, 1, 0, 0] },
    { login: 'carol', event_count: 2, pr_count: 2, review_count: 0, top_repos: ['repo-c'], repo_count: 1, last_active: new Date(Date.now() - 3 * 86_400_000).toISOString(), weekly_counts: [0, 0, 1, 1, 0, 0, 0] },
    { login: 'dave', event_count: 2, pr_count: 0, review_count: 0, top_repos: ['repo-d'], repo_count: 1, last_active: new Date(Date.now() - 4 * 86_400_000).toISOString(), weekly_counts: [0, 0, 0, 1, 1, 0, 0] },
    { login: 'eve', event_count: 1, pr_count: 0, review_count: 0, top_repos: ['repo-e'], repo_count: 1, last_active: new Date(Date.now() - 5 * 86_400_000).toISOString(), weekly_counts: [0, 0, 0, 0, 1, 0, 0] },
    { login: 'frank', event_count: 1, pr_count: 0, review_count: 0, top_repos: ['repo-f'], repo_count: 1, last_active: new Date(Date.now() - 6 * 86_400_000).toISOString(), weekly_counts: [0, 0, 0, 0, 0, 1, 0] },
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
  getUsageStats: vi.fn().mockResolvedValue({
    git_stats: {
      total_clones: 353,
      total_pushes: 159,
      total_fetches: 5,
      top_cloners: [
        { actor: 'github-actions[bot]', count: 352, is_bot: true },
        { actor: 'jmassardo', count: 1, is_bot: false },
      ],
      top_pushers: [
        { actor: 'jmassardo', count: 158, repos: ['org/repo-a', 'org/repo-b'] },
      ],
      daily_trend: [
        { date: '2026-03-20', clones: 10, pushes: 5, fetches: 1 },
        { date: '2026-03-21', clones: 8, pushes: 3, fetches: 0 },
      ],
    },
    api_stats: {
      total_requests: 0,
      top_users: [],
      top_endpoints: [],
      daily_trend: [],
      available: false,
    },
    bot_vs_human: {
      bot_events: 353,
      human_events: 164,
      bot_actors: ['github-actions[bot]'],
      human_actors: ['jmassardo'],
    },
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
      screen.getByText('Per-developer contribution metrics and security posture'),
    ).toBeInTheDocument();
  });

  it('renders "All teams" button and empty team note when no teams available', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('All teams')).toBeInTheDocument();
    expect(screen.getByText('No team data available')).toBeInTheDocument();
  });

  it('renders team filter buttons when teams are available', async () => {
    const { getTeams } = await import('../../api/healthSignals');
    vi.mocked(getTeams).mockResolvedValueOnce({
      teams: [
        { org: 'test-org', team_slug: 'platform', team_name: 'platform-team', members: ['alice', 'bob'] },
        { org: 'test-org', team_slug: 'backend', team_name: 'backend-team', members: ['carol'] },
      ],
    });

    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('All teams')).toBeInTheDocument();
    expect(await screen.findByText('platform-team')).toBeInTheDocument();
    expect(screen.getByText('backend-team')).toBeInTheDocument();
  });

  it('renders "Work distribution" section title', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(
      await screen.findByText(/Work distribution — last 30 days/),
    ).toBeInTheDocument();
  });

  it('PR authorship bars are clickable with role="button" and clickableBar class', async () => {
    renderWithProviders(<DevActivityPage />);

    // Wait for data to render
    await screen.findByText('PR authorship share');

    const barRows = document.querySelectorAll('.barRow.clickableBar');
    expect(barRows.length).toBeGreaterThanOrEqual(5); // at least 5 PR authorship bars

    // Every bar row should have role="button"
    barRows.forEach((row) => {
      expect(row.getAttribute('role')).toBe('button');
    });
  });

  it('"Others" row opens modal on click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    // We have 6 actors so there should be an "others" row (actors beyond top-5)
    const othersRow = await screen.findByText(/others \(/);
    await user.click(othersRow.closest('[role="button"]')!);

    // Modal should appear with title "Other contributors"
    expect(await screen.findByText('Other contributors')).toBeInTheDocument();

    // The modal table should contain the 6th contributor
    const modalTable = document.querySelector('.othersTable') as HTMLElement;
    expect(within(modalTable).getByText(/@frank/)).toBeInTheDocument();
  });

  it('activity concentration bars are clickable', async () => {
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Event activity share');

    // Concentration section also uses clickableBar rows
    const allClickableBars = document.querySelectorAll('.clickableBar[role="button"]');
    expect(allClickableBars.length).toBeGreaterThanOrEqual(6); // PR bars + concentration bars
  });

  it('warning text links are clickable when top actor >40%', async () => {
    renderWithProviders(<DevActivityPage />);

    // alice has >40% share → warning should appear
    const warningText = await screen.findByText(/accounts for/);
    expect(warningText).toBeInTheDocument();

    // The @alice text and pct% text should be clickable
    const warningContainer = warningText.closest('div')!;
    const clickableElements = warningContainer.querySelectorAll('.clickableText[role="button"]');
    expect(clickableElements.length).toBe(2); // @alice and pct%

    // Verify the actor name link
    const actorLink = within(warningContainer).getByText(`@${mockDevelopers[0].login}`);
    expect(actorLink.getAttribute('role')).toBe('button');
  });

  it('developer card stat numbers are clickable with clickableStat class', async () => {
    renderWithProviders(<DevActivityPage />);

    // Wait for dev cards to render
    await screen.findByText('Developer cards');

    const clickableStats = document.querySelectorAll('.clickableStat[role="button"]');
    // Each dev card has 3 clickable stats (repos, PRs, flags/detections)
    // With 6 actors we expect at least 6 × 3 = 18
    expect(clickableStats.length).toBeGreaterThanOrEqual(18);

    // Verify they contain expected text patterns
    const statTexts = Array.from(clickableStats).map((el) => el.textContent);
    expect(statTexts.some((t) => t?.includes('repos'))).toBe(true);
    expect(statTexts.some((t) => t?.includes('PRs'))).toBe(true);
  });

  it('shows empty state message when no events', async () => {
    const { getDevelopers } = await import('../../api/devActivity');
    vi.mocked(getDevelopers).mockResolvedValueOnce({
      developers: [],
      lookback_days: 90,
    });

    renderWithProviders(<DevActivityPage />);

    expect(
      await screen.findByText('No developer activity data found.'),
    ).toBeInTheDocument();
  });

  it('opens developer detail drawer when a card is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    // Wait for dev cards to render
    await screen.findByText('Developer cards');

    // Click the first dev card (alice)
    const aliceCard = screen.getByLabelText('View details for alice');
    await user.click(aliceCard);

    // Drawer should open with title "Developer details"
    expect(await screen.findByText('Developer details')).toBeInTheDocument();

    // Drawer content should show developer info
    const drawerPanel = screen.getByTestId('drawer-panel');
    expect(within(drawerPanel).getByText('@alice')).toBeInTheDocument();
  });

  it('drawer shows contribution stats with emoji labels', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Developer cards');
    const aliceCard = screen.getByLabelText('View details for alice');
    await user.click(aliceCard);

    const drawerPanel = await screen.findByTestId('drawer-panel');

    // Check contribution section
    expect(within(drawerPanel).getByText('Contributions')).toBeInTheDocument();
    expect(within(drawerPanel).getByText('Weekly Activity')).toBeInTheDocument();
  });

  it('drawer shows GitHub profile link with correct href', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Developer cards');
    const aliceCard = screen.getByLabelText('View details for alice');
    await user.click(aliceCard);

    const drawerPanel = await screen.findByTestId('drawer-panel');
    const profileLink = within(drawerPanel).getByText(/View GitHub profile/);
    expect(profileLink).toBeInTheDocument();
    expect(profileLink.closest('a')).toHaveAttribute('href', 'https://github.com/alice');
    expect(profileLink.closest('a')).toHaveAttribute('target', '_blank');
    expect(profileLink.closest('a')).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('closes drawer when backdrop is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Developer cards');
    const aliceCard = screen.getByLabelText('View details for alice');
    await user.click(aliceCard);

    // Drawer should be open
    expect(await screen.findByTestId('drawer-panel')).toBeInTheDocument();

    // Click backdrop to close
    const backdrop = screen.getByTestId('drawer-backdrop');
    await user.click(backdrop);

    // Drawer should be gone
    expect(screen.queryByTestId('drawer-panel')).not.toBeInTheDocument();
  });

  it('closes drawer when close button is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Developer cards');
    const aliceCard = screen.getByLabelText('View details for alice');
    await user.click(aliceCard);

    expect(await screen.findByTestId('drawer-panel')).toBeInTheDocument();

    // Click the close button
    const closeButton = screen.getByLabelText('Close');
    await user.click(closeButton);

    expect(screen.queryByTestId('drawer-panel')).not.toBeInTheDocument();
  });

  it('closes drawer on Escape key press', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Developer cards');
    const aliceCard = screen.getByLabelText('View details for alice');
    await user.click(aliceCard);

    expect(await screen.findByTestId('drawer-panel')).toBeInTheDocument();

    // Press Escape to close
    await user.keyboard('{Escape}');

    expect(screen.queryByTestId('drawer-panel')).not.toBeInTheDocument();
  });

  it('drawer has correct ARIA attributes', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Developer cards');
    const aliceCard = screen.getByLabelText('View details for alice');
    await user.click(aliceCard);

    const drawerPanel = await screen.findByTestId('drawer-panel');
    expect(drawerPanel).toHaveAttribute('role', 'dialog');
    expect(drawerPanel).toHaveAttribute('aria-modal', 'true');
    expect(drawerPanel).toHaveAttribute('aria-labelledby', 'dev-detail-title');
  });

  it('dev card opens drawer via keyboard Enter key', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Developer cards');
    const bobCard = screen.getByLabelText('View details for bob');
    bobCard.focus();
    await user.keyboard('{Enter}');

    const drawerPanel = await screen.findByTestId('drawer-panel');
    expect(within(drawerPanel).getByText('@bob')).toBeInTheDocument();
  });

  // ── Platform usage section tests ──────────────────────────────────────

  it('renders "Platform usage" section title', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(
      await screen.findByText(/Platform usage — last 30 days/),
    ).toBeInTheDocument();
  });

  it('renders Git operations card with metric values', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('Git operations')).toBeInTheDocument();
    expect(screen.getByText('353')).toBeInTheDocument();
    expect(screen.getByText('159')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('Clones')).toBeInTheDocument();
    expect(screen.getByText('Pushes')).toBeInTheDocument();
    expect(screen.getByText('Fetches')).toBeInTheDocument();
  });

  it('renders top cloners list in git operations widget', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('Top cloners')).toBeInTheDocument();
    expect(screen.getByText('github-actions[bot]')).toBeInTheDocument();
    // jmassardo appears in cloners and pushers widgets
    const jmassardoElements = screen.getAllByText('@jmassardo');
    expect(jmassardoElements.length).toBeGreaterThanOrEqual(1);
  });

  it('renders top pushers list in git operations widget', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('Top pushers')).toBeInTheDocument();
  });

  it('renders bot vs human indicator', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('Bot vs Human')).toBeInTheDocument();
    expect(screen.getByText(/Bot 68%/)).toBeInTheDocument();
    expect(screen.getByText(/Human 32%/)).toBeInTheDocument();
  });

  it('renders daily trend chart bars for git events', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('Daily trend')).toBeInTheDocument();
  });

  it('renders API usage card with disabled note when unavailable', async () => {
    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('API usage')).toBeInTheDocument();
    expect(
      screen.getByText('No API request events found in the last 30 days.'),
    ).toBeInTheDocument();
  });

  it('renders API usage card with docs link', async () => {
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('API usage');
    const link = screen.getByText('GitHub Enterprise audit log streaming settings');
    expect(link).toBeInTheDocument();
    expect(link.closest('a')).toHaveAttribute('target', '_blank');
    expect(link.closest('a')).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('renders API usage card with stats when available', async () => {
    const { getUsageStats } = await import('../../api/devActivity');
    vi.mocked(getUsageStats).mockResolvedValueOnce({
      git_stats: {
        total_clones: 0,
        total_pushes: 0,
        total_fetches: 0,
        top_cloners: [],
        top_pushers: [],
        daily_trend: [],
      },
      api_stats: {
        total_requests: 500,
        top_users: [
          { actor: 'admin-user', count: 200 },
          { actor: 'dev-user', count: 100 },
        ],
        top_endpoints: [
          { endpoint: 'GET /repos', count: 300 },
        ],
        daily_trend: [
          { date: '2026-03-20', requests: 250 },
          { date: '2026-03-21', requests: 250 },
        ],
        available: true,
      },
      bot_vs_human: {
        bot_events: 0,
        human_events: 0,
        bot_actors: [],
        human_actors: [],
      },
    });

    renderWithProviders(<DevActivityPage />);

    expect(await screen.findByText('API usage')).toBeInTheDocument();
    expect(await screen.findByText('500')).toBeInTheDocument();
    expect(screen.getByText('Total requests')).toBeInTheDocument();
    expect(screen.getByText('Unique users')).toBeInTheDocument();
    expect(screen.getByText('Unique endpoints')).toBeInTheDocument();
    expect(screen.getByText('Top API users')).toBeInTheDocument();
    expect(screen.getByText('@admin-user')).toBeInTheDocument();
    expect(screen.getByText('Top endpoints')).toBeInTheDocument();
    expect(screen.getByText('GET /repos')).toBeInTheDocument();
  });

  it('cloner bar rows are clickable with role="button"', async () => {
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Top cloners');
    // The bot cloner should render in italic
    const botLabel = screen.getByText('github-actions[bot]');
    expect(botLabel).toHaveStyle({ fontStyle: 'italic' });
    // It should be inside a clickable bar
    const barRow = botLabel.closest('.clickableBar');
    expect(barRow).not.toBeNull();
    expect(barRow?.getAttribute('role')).toBe('button');
  });

  it('developer cards show last active time', async () => {
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Developer cards');

    // Developer cards should show last active time
    const lastActiveElements = screen.getAllByText(/Last active/);
    expect(lastActiveElements.length).toBeGreaterThanOrEqual(1);
  });

  it('drawer shows top repos when available', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Developer cards');
    const aliceCard = screen.getByLabelText('View details for alice');
    await user.click(aliceCard);

    const drawerPanel = await screen.findByTestId('drawer-panel');
    expect(within(drawerPanel).getByText('Most Active Repos')).toBeInTheDocument();
    expect(within(drawerPanel).getByText(/repo-a/)).toBeInTheDocument();
  });

  it('drawer shows last active time', async () => {
    const user = userEvent.setup();
    renderWithProviders(<DevActivityPage />);

    await screen.findByText('Developer cards');
    const aliceCard = screen.getByLabelText('View details for alice');
    await user.click(aliceCard);

    const drawerPanel = await screen.findByTestId('drawer-panel');
    expect(within(drawerPanel).getByText(/Last active/)).toBeInTheDocument();
  });
});
