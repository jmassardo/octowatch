import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { PlatformUsagePage } from './index';

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts-mock" />,
}));

const mockSummaryResponse = {
  features: [
    {
      feature_area: 'actions',
      unique_actors: 42,
      active_days: 25,
      total_actions_minutes: 15000,
      total_actions_runs: 3200,
      total_copilot_suggestions: 0,
      total_copilot_acceptances: 0,
      total_copilot_credits: 0,
      total_git_clones: 0,
      total_git_pushes: 0,
      total_packages_published: 0,
    },
    {
      feature_area: 'copilot',
      unique_actors: 28,
      active_days: 20,
      total_actions_minutes: 0,
      total_actions_runs: 0,
      total_copilot_suggestions: 8500,
      total_copilot_acceptances: 4200,
      total_copilot_credits: 1200,
      total_git_clones: 0,
      total_git_pushes: 0,
      total_packages_published: 0,
    },
  ],
  period_days: 30,
};

const mockTrendsResponse = {
  trends: [
    {
      date: '2026-07-01',
      feature_area: 'actions',
      unique_actors: 10,
      actions_minutes: 500,
      copilot_credits: 0,
      git_clones: 0,
      git_pushes: 0,
    },
    {
      date: '2026-07-02',
      feature_area: 'actions',
      unique_actors: 12,
      actions_minutes: 600,
      copilot_credits: 0,
      git_clones: 0,
      git_pushes: 0,
    },
  ],
  period_days: 30,
};

const mockConsumersResponse = {
  consumers: [
    {
      actor_login: 'user1',
      org_slug: 'my-org',
      total_actions_minutes: 500,
      total_actions_runs: 100,
      total_copilot_suggestions: 0,
      total_copilot_acceptances: 0,
      total_copilot_credits: 0,
      total_git_clones: 0,
      total_git_pushes: 0,
      active_days: 15,
    },
  ],
  feature_area: 'actions',
  period_days: 30,
};

const mockAnomaliesResponse = {
  anomalies: [
    {
      id: 1,
      triggered_at: '2026-07-15T10:00:00Z',
      severity: 'high',
      confidence_score: 0.92,
      actor: 'badactor',
      org: 'my-org',
      rule_name: 'Unusual API usage',
      rule_slug: 'unusual-api',
      category: 'api',
    },
  ],
  period_days: 7,
};

beforeEach(() => {
  vi.resetAllMocks();
  global.fetch = vi.fn();
});

function mockFetchSuccess() {
  (global.fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => {
    if (url.includes('/platform-usage/summary')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockSummaryResponse),
        headers: new Headers({ 'Content-Type': 'application/json' }),
      });
    }
    if (url.includes('/platform-usage/trends')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockTrendsResponse),
        headers: new Headers({ 'Content-Type': 'application/json' }),
      });
    }
    if (url.includes('/platform-usage/top-consumers')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockConsumersResponse),
        headers: new Headers({ 'Content-Type': 'application/json' }),
      });
    }
    if (url.includes('/platform-usage/anomalies')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockAnomaliesResponse),
        headers: new Headers({ 'Content-Type': 'application/json' }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: () => Promise.resolve({}),
      headers: new Headers({ 'Content-Type': 'application/json' }),
    });
  });
}

describe('PlatformUsagePage', () => {
  it('renders the page header', () => {
    mockFetchSuccess();
    renderWithProviders(<PlatformUsagePage />);
    expect(screen.getByText('Platform Usage')).toBeInTheDocument();
  });

  it('shows loading state initially', () => {
    // Never resolve fetch to keep loading state
    (global.fetch as ReturnType<typeof vi.fn>).mockImplementation(() => new Promise(() => {}));
    renderWithProviders(<PlatformUsagePage />);
    // Skeleton cards should be present (they have aria-hidden)
    const skeletons = document.querySelectorAll('[aria-hidden="true"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('displays feature summary cards when data loads', async () => {
    mockFetchSuccess();
    renderWithProviders(<PlatformUsagePage />);

    await waitFor(() => {
      expect(screen.getByTestId('feature-card-actions')).toBeInTheDocument();
    });
    expect(screen.getByTestId('feature-card-copilot')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('tab switching works', async () => {
    mockFetchSuccess();
    const user = userEvent.setup();
    renderWithProviders(<PlatformUsagePage />);

    // Switch to Anomalies tab
    const anomaliesTab = screen.getByRole('tab', { name: 'Anomalies' });
    await user.click(anomaliesTab);

    await waitFor(() => {
      expect(screen.getByText('Unusual API usage')).toBeInTheDocument();
    });
  });

  it('displays trends chart on overview tab', async () => {
    mockFetchSuccess();
    renderWithProviders(<PlatformUsagePage />);

    await waitFor(() => {
      expect(screen.getByTestId('echarts-mock')).toBeInTheDocument();
    });
  });

  it('renders actions tab with top consumers', async () => {
    mockFetchSuccess();
    const user = userEvent.setup();
    renderWithProviders(<PlatformUsagePage />);

    const actionsTab = screen.getByRole('tab', { name: 'Actions' });
    await user.click(actionsTab);

    await waitFor(() => {
      expect(screen.getByText('user1')).toBeInTheDocument();
    });
  });
});
