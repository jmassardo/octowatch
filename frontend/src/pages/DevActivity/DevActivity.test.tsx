import { describe, it, expect, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { DevActivityPage } from './index';

// ---------------------------------------------------------------------------
// Mock helpers (vi.hoisted so they're available inside vi.mock factories)
// ---------------------------------------------------------------------------

const { mockEvents } = vi.hoisted(() => {
  const makeEvent = (actor: string, action: string, repo: string, daysAgo: number) => ({
    id: `evt-${actor}-${action}-${daysAgo}-${Math.random()}`,
    document_id: `doc-${Math.random()}`,
    created_at: new Date(Date.now() - daysAgo * 86_400_000).toISOString(),
    ingested_at: new Date().toISOString(),
    action,
    namespace: 'pull_request',
    actor,
    actor_id: 1,
    actor_is_bot: false,
    org: 'test-org',
    org_id: 1,
    repo,
    repo_id: 1,
    business: null,
    source_ip: '1.2.3.4',
    user_agent: null,
    geo_country_code: 'US',
    geo_city: 'SF',
    geo_is_proxy: false,
    data: {},
    ingestion_source: 'webhook',
    source_file_path: null,
  });

  // alice has ~53% share (10/19) to trigger the >40% warning
  const mockEvents = [
    ...Array.from({ length: 10 }, (_, i) => makeEvent('alice', 'pull_request.opened', 'repo-a', i)),
    ...Array.from({ length: 3 }, (_, i) => makeEvent('bob', 'pull_request.opened', 'repo-b', i)),
    ...Array.from({ length: 2 }, (_, i) => makeEvent('carol', 'pull_request.opened', 'repo-c', i)),
    ...Array.from({ length: 2 }, (_, i) => makeEvent('dave', 'push', 'repo-d', i)),
    ...Array.from({ length: 1 }, (_, i) => makeEvent('eve', 'push', 'repo-e', i)),
    ...Array.from({ length: 1 }, (_, i) => makeEvent('frank', 'push', 'repo-f', i)),
  ];

  return { mockEvents };
});

// ---------------------------------------------------------------------------
// Mock API modules
// ---------------------------------------------------------------------------

vi.mock('../../api/events', () => ({
  listEvents: vi.fn().mockResolvedValue({
    items: mockEvents,
    total: mockEvents.length,
    page: 1,
    page_size: 500,
  }),
}));

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
    const actorLink = within(warningContainer).getByText(`@${mockEvents[0].actor}`);
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
    const { listEvents } = await import('../../api/events');
    vi.mocked(listEvents).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      page_size: 500,
    } as never);

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
});
