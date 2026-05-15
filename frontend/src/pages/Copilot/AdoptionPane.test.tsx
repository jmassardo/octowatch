import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AdoptionPane } from './AdoptionPane';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
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
      { feature: 'IDE completions', pct: 87, color: '#3fb950' },
      { feature: 'IDE chat', pct: 62, color: '#58a6ff' },
      { feature: 'PR summaries', pct: 41, color: '#d29922' },
      { feature: 'CLI', pct: 23, color: '#f85149' },
      { feature: 'Knowledge bases', pct: 12, color: '#8b949e' },
    ],
    minimal_users: [
      { user: 'tom.jones', days_active: 2, last_feature: 'IDE chat' },
      { user: 'lisa.park', days_active: 1, last_feature: 'Completions' },
      { user: 'raj.kumar', days_active: 2, last_feature: 'PR summary' },
    ],
  }),
}));

function getDialog(): HTMLElement {
  return document.querySelector('.dialog')! as HTMLElement;
}

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

describe('AdoptionPane clickable stats', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it('makes tier cards clickable with role=button and tabIndex', async () => {
    renderPane();
    const powerCard = (await screen.findByText('Power Users')).closest('[role="button"]');
    expect(powerCard).toBeTruthy();
    expect(powerCard).toHaveAttribute('tabIndex', '0');
  });

  it('opens Power Users tier modal with power users table', async () => {
    const user = userEvent.setup();
    renderPane();
    const powerCard = (await screen.findByText('Power Users')).closest('[role="button"]')!;
    await user.click(powerCard);
    expect(screen.getByText('Power Users — 34 users')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText('sarah.chen')).toBeInTheDocument();
  });

  it('opens Minimal tier modal with minimal users table', async () => {
    const user = userEvent.setup();
    renderPane();
    const minimalCard = (await screen.findByText('Minimal')).closest('[role="button"]')!;
    await user.click(minimalCard);
    expect(screen.getByText('Minimal — 22 users')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText('tom.jones')).toBeInTheDocument();
  });

  it('opens Power Users tier modal showing tier description', async () => {
    const user = userEvent.setup();
    renderPane();
    const powerCard = (await screen.findByText('Power Users')).closest('[role="button"]')!;
    await user.click(powerCard);
    expect(screen.getByText('Power Users — 34 users')).toBeInTheDocument();
    const dialog = getDialog();
    // Modal shows the tier description for power users
    expect(within(dialog).getByText(/Active every day/)).toBeInTheDocument();
  });

  it('opens tier modal from stacked bar segment', async () => {
    const user = userEvent.setup();
    renderPane();
    // Wait for data to load
    await screen.findByText('Power Users');
    // Only power and minimal tier segments are clickable
    const segments = document.querySelectorAll('.stackedSegmentClickable');
    expect(segments.length).toBe(2);
    await user.click(segments[0] as HTMLElement);
    expect(screen.getByText('Power Users — 34 users')).toBeInTheDocument();
  });

  it('closes tier modal', async () => {
    const user = userEvent.setup();
    renderPane();
    const powerCard = (await screen.findByText('Power Users')).closest('[role="button"]')!;
    await user.click(powerCard);
    expect(screen.getByText('Power Users — 34 users')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /close/i }));
    expect(screen.queryByText('Power Users — 34 users')).not.toBeInTheDocument();
  });

  it('navigates to actor page when clicking days active in power users table', async () => {
    const user = userEvent.setup();
    renderPane();
    const daysBtn = (await screen.findByText('45d')).closest('[role="button"]')!;
    await user.click(daysBtn);
    expect(mockNavigate).toHaveBeenCalledWith('/actors/sarah.chen');
  });

  it('navigates to actor page when clicking features used in power users table', async () => {
    const user = userEvent.setup();
    renderPane();
    // Wait for data to load
    await screen.findByText('sarah.chen');
    // The features_used value for sarah.chen is 5 — get the clickable stat
    const clickableStats = screen
      .getAllByRole('button')
      .filter((el) => el.classList.contains('clickableStat'));
    const featBtn = clickableStats.find((el) => el.textContent === '5');
    expect(featBtn).toBeTruthy();
    await user.click(featBtn!);
    expect(mockNavigate).toHaveBeenCalledWith('/actors/sarah.chen');
  });

  it('makes feature adoption bars clickable', async () => {
    renderPane();
    const ideRow = (await screen.findByText('IDE completions')).closest('[role="button"]');
    expect(ideRow).toBeTruthy();
    expect(ideRow).toHaveAttribute('tabIndex', '0');
  });

  it('opens feature adoption modal when clicking a feature bar', async () => {
    const user = userEvent.setup();
    renderPane();
    const ideRow = (await screen.findByText('IDE completions')).closest('[role="button"]')!;
    await user.click(ideRow);
    expect(screen.getByText('IDE completions — adoption details')).toBeInTheDocument();
    const dialog = getDialog();
    expect(within(dialog).getByText(/87%/)).toBeInTheDocument();
  });

  it('shows feature adoption gaps section', async () => {
    renderPane();
    await screen.findByText('Power Users');
    expect(screen.getByText('Feature adoption gaps')).toBeInTheDocument();
  });

  it('shows Opportunity badge for features below 30% adoption', async () => {
    renderPane();
    await screen.findByText('Power Users');
    // CLI (23%) and Knowledge bases (12%) are below 30%
    const badges = screen.getAllByText('Opportunity');
    expect(badges.length).toBe(2);
  });

  it('shows growth opportunities callout', async () => {
    renderPane();
    await screen.findByText('Power Users');
    expect(
      screen.getByText(/Features below 30% adoption represent growth opportunities/),
    ).toBeInTheDocument();
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

  it('makes minimal users Days active cells clickable', async () => {
    renderPane();
    await screen.findByText('tom.jones');
    const clickableStats = screen
      .getAllByRole('button')
      .filter((el) => el.classList.contains('clickableStat'));
    // Should have power users stats + minimal users stats
    expect(clickableStats.length).toBeGreaterThanOrEqual(6);
  });

  it('opens minimal user modal with activity summary', async () => {
    const user = userEvent.setup();
    renderPane();
    await screen.findByText('tom.jones');
    const clickableStats = screen
      .getAllByRole('button')
      .filter((el) => el.classList.contains('clickableStat'));
    // Find one that represents a days_active count for minimal users (value '2')
    const minimalBtn = clickableStats.find((el) => el.textContent === '2');
    expect(minimalBtn).toBeTruthy();
    await user.click(minimalBtn!);
    const dialog = getDialog();
    expect(within(dialog).getByText(/Copilot activity/)).toBeInTheDocument();
  });
});
