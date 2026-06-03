import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/utils';
import { DashboardPage } from './index';

vi.mock('../../components/charts/ContributionCalendar', () => ({
  ContributionCalendar: () => <div data-testid="contribution-calendar" />,
}));

vi.mock('../../api/dashboardConfig', () => ({
  getDashboardConfig: vi.fn().mockResolvedValue({
    id: 'test-id',
    user_id: 'testuser',
    layout: [],
    persona: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }),
  updateDashboardConfig: vi.fn().mockResolvedValue({
    id: 'test-id',
    user_id: 'testuser',
    layout: [],
    persona: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }),
  getWidgetCatalog: vi.fn().mockResolvedValue({
    widgets: [
      {
        id: 'security-overview',
        title: 'Security Overview',
        description: 'desc',
        category: 'security',
        default_w: 6,
        default_h: 3,
      },
      {
        id: 'event-volume',
        title: 'Event Volume',
        description: 'desc',
        category: 'activity',
        default_w: 4,
        default_h: 3,
      },
    ],
  }),
}));

const mockGetSystemHealth = vi.fn().mockResolvedValue({
  ingestion_healthy: true,
  last_event_at: '2025-03-15T00:00:00Z',
  gap_detected: false,
  gap_duration_minutes: null,
});

vi.mock('../../api/healthSignals', () => ({
  getSystemHealth: (...args: unknown[]) => mockGetSystemHealth(...args),
}));

describe('DashboardPage', () => {
  /* ---------------------------------------------------------------- */
  /*  Page header                                                      */
  /* ---------------------------------------------------------------- */

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('octowatch-onboarding-complete', 'true');
    mockGetSystemHealth.mockReset();
    mockGetSystemHealth.mockResolvedValue({
      ingestion_healthy: true,
      last_event_at: '2025-03-15T00:00:00Z',
      gap_detected: false,
      gap_duration_minutes: null,
    });
  });

  it('renders the page title', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.getByRole('heading', { name: /Dashboard ·/i })).toBeInTheDocument();
  });

  it('renders the page subtitle with last synced time', async () => {
    renderWithProviders(<DashboardPage />);

    // systemHealth resolves asynchronously with last_event_at
    expect(await screen.findByText(/last synced:/i)).toBeInTheDocument();
  });

  it('shows fallback subtitle when no system health data', () => {
    mockGetSystemHealth.mockResolvedValue({
      gap_detected: false,
      gap_duration_minutes: null,
      last_event_at: null,
    });
    renderWithProviders(<DashboardPage />);

    expect(screen.getByText(/activity across your organizations/i)).toBeInTheDocument();
  });

  it('shows org label in page title', () => {
    renderWithProviders(<DashboardPage />);

    // Default org context is empty string → "All organizations"
    expect(screen.getByText(/All organizations/)).toBeInTheDocument();
  });

  it('does not render removed security pills', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.queryByText(/unresolved secrets/)).not.toBeInTheDocument();
    expect(screen.queryByText(/feature disables \(7d\)/)).not.toBeInTheDocument();
    expect(screen.queryByText(/open threats/)).not.toBeInTheDocument();
    expect(screen.queryByText(/API calls \(24h\)/)).not.toBeInTheDocument();
  });

  it('does not show hardcoded "94.2%" or "1.8M"', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.queryByText('94.2%')).not.toBeInTheDocument();
    expect(screen.queryByText('1.8M')).not.toBeInTheDocument();
  });

  it('does not render ingestion banner when no gap detected', () => {
    renderWithProviders(<DashboardPage />);
    expect(screen.queryByText(/Data ingestion gap detected/)).not.toBeInTheDocument();
  });

  it('does not render hardcoded alert text', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.queryByText(/Workflow failure rate.*\+12%/)).not.toBeInTheDocument();
    expect(screen.queryByText(/PR cycle time.*platform-team/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Deploy frequency.*\+28%/)).not.toBeInTheDocument();
  });

  it('does not render "Open threats by severity" card', () => {
    renderWithProviders(<DashboardPage />);

    expect(screen.queryByText('Open threats by severity')).not.toBeInTheDocument();
  });
});
