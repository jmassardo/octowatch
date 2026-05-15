import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { CustomDashboardPage } from './index';

// Mock the API calls
vi.mock('../../api/dashboardConfig', () => ({
  getDashboardConfig: vi.fn().mockResolvedValue({
    id: 'test-id',
    user_id: 'testuser',
    layout: [
      { widget_id: 'sync-health', x: 0, y: 0, w: 4, h: 3 },
      { widget_id: 'event-volume', x: 4, y: 0, w: 6, h: 3 },
    ],
    persona: 'platform-engineer',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }),
  updateDashboardConfig: vi.fn().mockResolvedValue({
    id: 'test-id',
    user_id: 'testuser',
    layout: [],
    persona: 'platform-engineer',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }),
  getWidgetCatalog: vi.fn().mockResolvedValue({
    widgets: [
      {
        id: 'sync-health',
        title: 'Sync Health',
        description: 'Current sync status',
        category: 'operations',
        default_w: 4,
        default_h: 3,
      },
      {
        id: 'event-volume',
        title: 'Event Volume',
        description: '24-hour event activity',
        category: 'activity',
        default_w: 6,
        default_h: 3,
      },
      {
        id: 'copilot-usage',
        title: 'Copilot Usage',
        description: 'Adoption snapshot',
        category: 'copilot',
        default_w: 4,
        default_h: 3,
      },
    ],
  }),
  getPersonas: vi.fn().mockResolvedValue({
    personas: [
      {
        id: 'security-analyst',
        label: 'Security Analyst',
        description: 'Focus on threats',
        default_layout: [],
      },
    ],
  }),
}));

// Mock react-grid-layout since it needs DOM measurements
vi.mock('react-grid-layout', () => {
  function MockResponsive({
    children,
    className,
  }: {
    children: React.ReactNode;
    className?: string;
  }) {
    return (
      <div data-testid="grid-layout" className={className}>
        {children}
      </div>
    );
  }
  MockResponsive.displayName = 'MockResponsive';

  return {
    Responsive: MockResponsive,
    verticalCompactor: () => [],
  };
});

describe('CustomDashboardPage', () => {
  it('renders the page header', async () => {
    renderWithProviders(<CustomDashboardPage />, { route: '/dashboard/custom' });

    expect(await screen.findByText('Custom Dashboard')).toBeInTheDocument();
  });

  it('renders the toolbar with Add widgets and Change persona buttons', async () => {
    renderWithProviders(<CustomDashboardPage />, { route: '/dashboard/custom' });

    expect(await screen.findByRole('button', { name: /add widgets/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /change persona/i })).toBeInTheDocument();
  });

  it('renders widgets from the loaded config', async () => {
    renderWithProviders(<CustomDashboardPage />, { route: '/dashboard/custom' });

    // Wait for data to load and widgets to render
    expect(await screen.findByText('Sync Health')).toBeInTheDocument();
    expect(screen.getByText('Event Volume')).toBeInTheDocument();
  });

  it('renders remove buttons for each widget', async () => {
    renderWithProviders(<CustomDashboardPage />, { route: '/dashboard/custom' });

    expect(await screen.findByRole('button', { name: /remove sync health/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /remove event volume/i })).toBeInTheDocument();
  });

  it('opens the widget catalog when Add widgets is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CustomDashboardPage />, { route: '/dashboard/custom' });

    await screen.findByText('Custom Dashboard');
    await user.click(screen.getByRole('button', { name: /add widgets/i }));

    expect(screen.getByText('Widget catalog')).toBeInTheDocument();
  });

  it('opens the persona selector when Change persona is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CustomDashboardPage />, { route: '/dashboard/custom' });

    await screen.findByText('Custom Dashboard');
    await user.click(screen.getByRole('button', { name: /change persona/i }));

    expect(screen.getByText('Security Analyst')).toBeInTheDocument();
    expect(screen.getByText('Engineering Manager')).toBeInTheDocument();
    expect(screen.getByText('Platform Engineer')).toBeInTheDocument();
    expect(screen.getByText('Executive')).toBeInTheDocument();
  });
});
