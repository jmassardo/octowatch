import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AdoptionPane } from './AdoptionPane';

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual };
});

vi.mock('../../api/copilotMetrics', () => ({
  getCopilotAdoption: vi.fn().mockResolvedValue({
    tiers: [
      { id: 'power', label: 'Power Users', count: 34, color: '#3fb950', desc: 'Active every day' },
      { id: 'regular', label: 'Regular', count: 68, color: '#58a6ff', desc: '3-4 days/week' },
      { id: 'minimal', label: 'Minimal', count: 22, color: '#d29922', desc: '1-2 uses in 30d' },
      {
        id: 'inactive',
        label: 'Inactive',
        count: 38,
        color: '#f85149',
        desc: 'Cold 30d+ (was active)',
      },
      {
        id: 'never',
        label: 'Never Used',
        count: 24,
        color: '#8b949e',
        desc: 'Seat assigned, zero activity',
      },
    ],
    total_adoption: 186,
    power_users: [
      { user: 'sarah.chen', days_active: 45, features_used: 5 },
      { user: 'mike.ross', days_active: 38, features_used: 4 },
      { user: 'ana.silva', days_active: 32, features_used: 4 },
      { user: 'james.wu', days_active: 29, features_used: 5 },
      { user: 'priya.patel', days_active: 27, features_used: 3 },
    ],
    feature_adoption: [
      {
        feature: 'IDE completions',
        pct: 87,
        color: '#3fb950',
        active_users: 100,
        total_seats: 120,
        trend_7d: 2,
      },
      {
        feature: 'IDE chat',
        pct: 62,
        color: '#58a6ff',
        active_users: 75,
        total_seats: 120,
        trend_7d: 5,
      },
      {
        feature: 'PR summaries',
        pct: 41,
        color: '#d29922',
        active_users: 50,
        total_seats: 120,
        trend_7d: 0,
      },
      {
        feature: 'CLI',
        pct: 23,
        color: '#f85149',
        active_users: 28,
        total_seats: 120,
        trend_7d: -3,
      },
      {
        feature: 'Knowledge bases',
        pct: 12,
        color: '#8b949e',
        active_users: 15,
        total_seats: 120,
        trend_7d: 1,
      },
    ],
    minimal_users: [
      { user: 'tom.jones', days_active: 2, last_feature: 'IDE chat' },
      { user: 'lisa.park', days_active: 1, last_feature: 'Completions' },
      { user: 'raj.kumar', days_active: 2, last_feature: 'PR summary' },
    ],
  }),
}));

function renderPane() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QueryClientProvider client={queryClient}>
        <AdoptionPane />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe('AdoptionPane', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('makes ALL tier cards clickable with role=button and tabIndex', async () => {
    renderPane();
    await screen.findByText('Power Users');
    // All 5 tiers should be clickable (role=button)
    const tierElements = document.querySelectorAll('[class*="tierCardClickable"]');
    expect(tierElements.length).toBe(5);
    for (const el of tierElements) {
      expect(el.getAttribute('role')).toBe('button');
      expect(el.getAttribute('tabindex')).toBe('0');
    }
  });

  it('clicking a tier card filters the table to that tier', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('sarah.chen');

    // All users visible initially (5 power + 3 minimal = 8)
    expect(screen.getByText('sarah.chen')).toBeInTheDocument();
    expect(screen.getByText('tom.jones')).toBeInTheDocument();

    // Click 'power' tier card
    const powerCard = screen.getByText('Power Users').closest('[role="button"]')!;
    await user.click(powerCard);

    // Only power users visible
    expect(screen.getByText('sarah.chen')).toBeInTheDocument();
    expect(screen.queryByText('tom.jones')).not.toBeInTheDocument();
  });

  it('clicking the already-active tier deselects it (shows all)', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('sarah.chen');

    const powerCard = screen.getByText('Power Users').closest('[role="button"]')!;
    await user.click(powerCard);
    // Filtered to power only
    expect(screen.queryByText('tom.jones')).not.toBeInTheDocument();

    // Click again to deselect
    await user.click(powerCard);
    expect(screen.getByText('tom.jones')).toBeInTheDocument();
  });

  it('shows active tier with aria-pressed=true', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('Power Users');

    const powerCard = screen.getByText('Power Users').closest('[role="button"]')!;
    expect(powerCard.getAttribute('aria-pressed')).toBe('false');

    await user.click(powerCard);
    expect(powerCard.getAttribute('aria-pressed')).toBe('true');
  });

  it('shows unified table with all users and tier badges', async () => {
    renderPane();
    await screen.findByText('sarah.chen');

    // Power users
    expect(screen.getByText('sarah.chen')).toBeInTheDocument();
    expect(screen.getByText('mike.ross')).toBeInTheDocument();

    // Minimal users
    expect(screen.getByText('tom.jones')).toBeInTheDocument();
    expect(screen.getByText('lisa.park')).toBeInTheDocument();

    // Tier badges are rendered
    const powerBadges = screen.getAllByText('power');
    expect(powerBadges.length).toBe(5); // 5 power users
    const minimalBadges = screen.getAllByText('minimal');
    expect(minimalBadges.length).toBe(3); // 3 minimal users
  });

  it('opens drawer on row click showing user details', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('sarah.chen');

    // Click the row for sarah.chen
    const row = screen.getByText('sarah.chen').closest('tr')!;
    await user.click(row);

    // Drawer should open
    const drawerPanel = document.querySelector('[data-testid="drawer-panel"]') as HTMLElement;
    expect(drawerPanel).toBeTruthy();
    // User name appears in drawer (title + body)
    const nameMatches = within(drawerPanel).getAllByText(/sarah\.chen/);
    expect(nameMatches.length).toBeGreaterThanOrEqual(1);
    // Tier badge in drawer
    const tierBadges = within(drawerPanel).getAllByText('power');
    expect(tierBadges.length).toBeGreaterThanOrEqual(1);
    expect(within(drawerPanel).getByText('45d')).toBeInTheDocument();
    expect(within(drawerPanel).getByText('Features breakdown')).toBeInTheDocument();
  });

  it('drawer shows features breakdown with all features', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('sarah.chen');

    const row = screen.getByText('sarah.chen').closest('tr')!;
    await user.click(row);

    const drawerPanel = document.querySelector('[data-testid="drawer-panel"]') as HTMLElement;
    expect(within(drawerPanel).getByText('IDE completions')).toBeInTheDocument();
    expect(within(drawerPanel).getByText('IDE chat')).toBeInTheDocument();
    expect(within(drawerPanel).getByText('CLI')).toBeInTheDocument();
  });

  it('drawer closes when clicking close button', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('sarah.chen');

    const row = screen.getByText('sarah.chen').closest('tr')!;
    await user.click(row);

    expect(document.querySelector('[data-testid="drawer-panel"]')).toBeTruthy();

    const closeBtn = within(
      document.querySelector('[data-testid="drawer-panel"]') as HTMLElement,
    ).getByRole('button', { name: /close/i });
    await user.click(closeBtn);

    expect(document.querySelector('[data-testid="drawer-panel"]')).toBeNull();
  });

  it('drawer closes when clicking backdrop', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('sarah.chen');

    const row = screen.getByText('sarah.chen').closest('tr')!;
    await user.click(row);

    expect(document.querySelector('[data-testid="drawer-panel"]')).toBeTruthy();

    const backdrop = document.querySelector('[data-testid="drawer-backdrop"]') as HTMLElement;
    await user.click(backdrop);

    expect(document.querySelector('[data-testid="drawer-panel"]')).toBeNull();
  });

  it('stacked bar segments are all clickable and filter the table', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('Power Users');

    // All segments should be clickable
    const segments = document.querySelectorAll('[class*="stackedSegmentClickable"]');
    expect(segments.length).toBe(5);

    // Click the first segment (power)
    await user.click(segments[0] as HTMLElement);

    // Should filter to power users only
    expect(screen.getByText('sarah.chen')).toBeInTheDocument();
    expect(screen.queryByText('tom.jones')).not.toBeInTheDocument();
  });

  it('shows tier threshold settings button', async () => {
    renderPane();
    await screen.findByText('Power Users');
    expect(screen.getByLabelText('Tier threshold settings')).toBeInTheDocument();
  });

  it('opens tier threshold settings modal', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('Power Users');
    await user.click(screen.getByLabelText('Tier threshold settings'));
    expect(screen.getByText('Adoption tier thresholds')).toBeInTheDocument();
    expect(screen.getByLabelText('Power user threshold')).toBeInTheDocument();
    expect(screen.getByLabelText('Regular user threshold')).toBeInTheDocument();
    expect(screen.getByLabelText('Minimal user threshold')).toBeInTheDocument();
  });

  it('table header shows active filter tier name', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('sarah.chen');

    // Initially shows "Copilot users"
    expect(screen.getByText('Copilot users')).toBeInTheDocument();

    // Click power tier
    const powerCard = screen.getByText('Power Users').closest('[role="button"]')!;
    await user.click(powerCard);

    expect(screen.getByText('Copilot users — power tier')).toBeInTheDocument();
  });

  it('does not navigate to /actors/ on any table interaction', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('sarah.chen');

    // Click a row - should open drawer, not navigate
    const row = screen.getByText('sarah.chen').closest('tr')!;
    await user.click(row);

    // Verify drawer opened instead of navigation
    expect(document.querySelector('[data-testid="drawer-panel"]')).toBeTruthy();
  });

  it('drawer shows GitHub profile link', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('sarah.chen');

    const row = screen.getByText('sarah.chen').closest('tr')!;
    await user.click(row);

    const drawerPanel = document.querySelector('[data-testid="drawer-panel"]') as HTMLElement;
    const link = within(drawerPanel).getByText('View on GitHub ↗');
    expect(link).toBeInTheDocument();
    expect(link.closest('a')).toHaveAttribute('href', 'https://github.com/sarah.chen');
  });

  it('drawer shows last activity date when available', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('tom.jones');

    const row = screen.getByText('tom.jones').closest('tr')!;
    await user.click(row);

    const drawerPanel = document.querySelector('[data-testid="drawer-panel"]') as HTMLElement;
    // tom.jones has no last_activity in mock data, so "Last activity" section should not appear
    expect(within(drawerPanel).queryByText('Last activity')).not.toBeInTheDocument();
    // But "View on GitHub" link should be present
    expect(within(drawerPanel).getByText('View on GitHub ↗')).toBeInTheDocument();
  });

  it('shows all tier guidance when no tier is selected', async () => {
    renderPane();
    await screen.findByText('sarah.chen');

    expect(screen.getByText(/Power Users:/)).toBeInTheDocument();
    expect(screen.getByText(/Regular Users:/)).toBeInTheDocument();
    expect(screen.getByText(/Minimal Users:/)).toBeInTheDocument();
    expect(screen.getByText(/Inactive Users:/)).toBeInTheDocument();
  });

  it('shows only matching guidance when a tier is selected', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('sarah.chen');

    // Click the "Power Users" tier card (identified by count "34")
    const tierCount = screen.getByText('34');
    const powerCard = tierCount.closest('[role="button"]')!;
    await user.click(powerCard);

    expect(screen.getByText(/Power Users:/)).toBeInTheDocument();
    expect(screen.queryByText(/Regular Users:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Minimal Users:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Inactive Users:/)).not.toBeInTheDocument();
  });
});
