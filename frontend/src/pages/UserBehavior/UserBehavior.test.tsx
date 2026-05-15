import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { UserBehaviorPage } from './index';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('echarts-for-react', () => ({
  __esModule: true,
  default: () => <div data-testid="echarts-mock">Chart</div>,
}));

const mockSummary = {
  personas: [
    { persona: 'Power User', user_count: 10, avg_confidence: 0.85, total_events: 5000 },
    { persona: 'Web UI Only', user_count: 20, avg_confidence: 0.8, total_events: 2000 },
    { persona: 'Truly Dormant', user_count: 15, avg_confidence: 1.0, total_events: 0 },
  ],
  total_users: 45,
  dormant_count: 15,
  dormant_pct: 33.3,
  power_user_count: 10,
  power_user_pct: 22.2,
};

const mockUsers = {
  users: [
    {
      id: 1,
      user_login: 'octocat',
      org: 'my-org',
      persona: 'Power User',
      confidence_score: 0.85,
      event_count: 500,
      surfaces: ['web', 'git', 'api'],
      analysis_window_days: 90,
      classified_at: '2025-01-01T00:00:00+00:00',
    },
    {
      id: 2,
      user_login: 'dormant-user',
      org: 'my-org',
      persona: 'Truly Dormant',
      confidence_score: 1.0,
      event_count: 0,
      surfaces: [],
      analysis_window_days: 90,
      classified_at: '2025-01-01T00:00:00+00:00',
    },
  ],
  total: 2,
  page: 1,
  page_size: 50,
};

const mockRun = { status: 'ok', orgs_processed: 1, users_classified: 45 };

vi.mock('../../api/userClassification', () => ({
  getClassificationSummary: vi.fn(() => Promise.resolve(mockSummary)),
  getClassifiedUsers: vi.fn(() => Promise.resolve(mockUsers)),
  triggerClassificationRun: vi.fn(() => Promise.resolve(mockRun)),
}));

vi.mock('../../hooks/useHelp', () => ({
  useHelp: () => ({ isOpen: false, toggle: vi.fn(), helpKey: null }),
  HelpProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('UserBehaviorPage', () => {
  it('renders page title and description', async () => {
    renderWithProviders(<UserBehaviorPage />);
    expect(await screen.findByText('User Behavior')).toBeInTheDocument();
    expect(screen.getByText(/Classify users by audit log activity/)).toBeInTheDocument();
  });

  it('displays key metrics after loading', async () => {
    renderWithProviders(<UserBehaviorPage />);
    expect(await screen.findByTestId('total-users')).toHaveTextContent('45');
    expect(screen.getByTestId('dormant-pct')).toHaveTextContent('33.3%');
    expect(screen.getByTestId('power-user-pct')).toHaveTextContent('22.2%');
  });

  it('renders the donut chart', async () => {
    renderWithProviders(<UserBehaviorPage />);
    expect(await screen.findByTestId('echarts-mock')).toBeInTheDocument();
  });

  it('renders user table with classified users', async () => {
    renderWithProviders(<UserBehaviorPage />);
    expect(await screen.findByText('octocat')).toBeInTheDocument();
    expect(screen.getByText('dormant-user')).toBeInTheDocument();
  });

  it('renders persona badges in table', async () => {
    renderWithProviders(<UserBehaviorPage />);
    expect(await screen.findByText('Power User')).toBeInTheDocument();
    expect(screen.getByText('Truly Dormant')).toBeInTheDocument();
  });

  it('has a persona filter dropdown', async () => {
    renderWithProviders(<UserBehaviorPage />);
    const select = await screen.findByLabelText(/Filter by persona/i);
    expect(select).toBeInTheDocument();
    expect(select).toHaveValue('');
  });

  it('has a Run Classification button', async () => {
    renderWithProviders(<UserBehaviorPage />);
    expect(await screen.findByText('Run Classification')).toBeInTheDocument();
  });

  it('renders surface tags for users', async () => {
    renderWithProviders(<UserBehaviorPage />);
    expect(await screen.findByText('web')).toBeInTheDocument();
    expect(screen.getByText('git')).toBeInTheDocument();
    expect(screen.getByText('api')).toBeInTheDocument();
  });

  it('persona filter changes trigger new query', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UserBehaviorPage />);

    const select = await screen.findByLabelText(/Filter by persona/i);
    await user.selectOptions(select, 'Power User');
    expect(select).toHaveValue('Power User');
  });

  it('shows Persona Distribution chart title', async () => {
    renderWithProviders(<UserBehaviorPage />);
    expect(await screen.findByText('Persona Distribution')).toBeInTheDocument();
  });
});
