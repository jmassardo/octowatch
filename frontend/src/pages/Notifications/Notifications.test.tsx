import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { NotificationsPage } from './index';

const mockListNotifications = vi.fn();
const mockMarkNotificationRead = vi.fn();
const mockMarkAllNotificationsRead = vi.fn();
const mockGetPreferences = vi.fn();
const mockUpdatePreferences = vi.fn();

vi.mock('../../api/notifications', () => ({
  listNotifications: (...args: unknown[]) => mockListNotifications(...args),
  markNotificationRead: (...args: unknown[]) => mockMarkNotificationRead(...args),
  markAllNotificationsRead: (...args: unknown[]) => mockMarkAllNotificationsRead(...args),
  getNotificationPreferences: (...args: unknown[]) => mockGetPreferences(...args),
  updateNotificationPreferences: (...args: unknown[]) => mockUpdatePreferences(...args),
}));

const mockNotifications = {
  items: [
    {
      id: 1,
      user_id: 'testuser',
      title: 'Critical detection found',
      message: 'Suspicious API key exposure detected in acme-corp/frontend',
      severity: 'critical' as const,
      read: false,
      source: 'detection' as const,
      link: '/threats',
      created_at: new Date().toISOString(),
    },
    {
      id: 2,
      user_id: 'testuser',
      title: 'Sync completed',
      message: 'Enterprise data sync finished successfully',
      severity: 'info' as const,
      read: true,
      source: 'sync' as const,
      link: null,
      created_at: new Date(Date.now() - 3600000).toISOString(),
    },
    {
      id: 3,
      user_id: 'testuser',
      title: 'High severity alert',
      message: 'Unusual branch protection removal in main-repo',
      severity: 'warning' as const,
      read: false,
      source: 'detection' as const,
      link: '/threats',
      created_at: new Date(Date.now() - 7200000).toISOString(),
    },
  ],
  total: 3,
  page: 1,
  page_size: 20,
  has_next: false,
  unread_count: 2,
};

const mockPreferences = {
  in_app_enabled: true,
  email_enabled: false,
  slack_enabled: false,
  severity_filter: 'info',
  detection_alerts: true,
  sync_alerts: true,
  system_alerts: true,
  updated_at: new Date().toISOString(),
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/notifications']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/notifications" element={<NotificationsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('NotificationsPage', () => {
  beforeEach(() => {
    mockListNotifications.mockReset();
    mockMarkNotificationRead.mockReset();
    mockMarkAllNotificationsRead.mockReset();
    mockGetPreferences.mockReset();
    mockUpdatePreferences.mockReset();

    mockListNotifications.mockResolvedValue(mockNotifications);
    mockGetPreferences.mockResolvedValue(mockPreferences);
    mockMarkNotificationRead.mockResolvedValue(mockNotifications.items[0]);
    mockMarkAllNotificationsRead.mockResolvedValue({ updated: 2 });
    mockUpdatePreferences.mockResolvedValue(mockPreferences);
  });

  /* ------------------------------------------------------------------ */
  /*  Page structure                                                      */
  /* ------------------------------------------------------------------ */

  it('renders page title and description', async () => {
    renderPage();

    expect(screen.getByRole('heading', { level: 1, name: /notifications/i })).toBeInTheDocument();
    expect(screen.getByText(/view and manage your notification alerts/i)).toBeInTheDocument();
  });

  it('renders tab buttons', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/notifications/i, { selector: 'button' })).toBeInTheDocument();
    });
    expect(screen.getByText('Preferences', { selector: 'button' })).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Notification list                                                   */
  /* ------------------------------------------------------------------ */

  it('renders notification items', async () => {
    renderPage();

    expect(await screen.findByText('Critical detection found')).toBeInTheDocument();
    expect(screen.getByText('Sync completed')).toBeInTheDocument();
    expect(screen.getByText('High severity alert')).toBeInTheDocument();
  });

  it('shows severity badges', async () => {
    renderPage();

    await screen.findByText('Critical detection found');

    expect(screen.getByText('critical')).toBeInTheDocument();
    expect(screen.getByText('info')).toBeInTheDocument();
    expect(screen.getByText('warning')).toBeInTheDocument();
  });

  it('shows source badges', async () => {
    renderPage();

    await screen.findByText('Critical detection found');

    const detectionBadges = screen.getAllByText('detection');
    expect(detectionBadges.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('sync')).toBeInTheDocument();
  });

  it('shows unread count in tab', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/notifications \(2\)/i, { selector: 'button' })).toBeInTheDocument();
    });
  });

  /* ------------------------------------------------------------------ */
  /*  Filters                                                             */
  /* ------------------------------------------------------------------ */

  it('renders severity filter', async () => {
    renderPage();

    await screen.findByText('Critical detection found');

    const select = screen.getByLabelText('Filter by severity');
    expect(select).toBeInTheDocument();
  });

  it('renders read status filter', async () => {
    renderPage();

    await screen.findByText('Critical detection found');

    const select = screen.getByLabelText('Filter by read status');
    expect(select).toBeInTheDocument();
  });

  it('renders source filter', async () => {
    renderPage();

    await screen.findByText('Critical detection found');

    const select = screen.getByLabelText('Filter by source');
    expect(select).toBeInTheDocument();
  });

  it('calls API with severity filter when changed', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Critical detection found');

    const select = screen.getByLabelText('Filter by severity');
    await user.selectOptions(select, 'critical');

    await waitFor(() => {
      expect(mockListNotifications).toHaveBeenCalledWith(
        expect.objectContaining({ severity: 'critical' }),
      );
    });
  });

  /* ------------------------------------------------------------------ */
  /*  Mark as read                                                        */
  /* ------------------------------------------------------------------ */

  it('shows Mark all read button', async () => {
    renderPage();

    await screen.findByText('Critical detection found');

    expect(screen.getByRole('button', { name: /mark all read/i })).toBeInTheDocument();
  });

  it('calls markAllNotificationsRead when Mark all read is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Critical detection found');

    await user.click(screen.getByRole('button', { name: /mark all read/i }));

    await waitFor(() => {
      expect(mockMarkAllNotificationsRead).toHaveBeenCalled();
    });
  });

  /* ------------------------------------------------------------------ */
  /*  Empty state                                                         */
  /* ------------------------------------------------------------------ */

  it('shows empty state when no notifications', async () => {
    mockListNotifications.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      has_next: false,
      unread_count: 0,
    });

    renderPage();

    expect(await screen.findByText('No notifications')).toBeInTheDocument();
    expect(screen.getByText(/you're all caught up/i)).toBeInTheDocument();
  });

  /* ------------------------------------------------------------------ */
  /*  Preferences tab                                                     */
  /* ------------------------------------------------------------------ */

  it('switches to preferences tab', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Critical detection found');

    await user.click(screen.getByText('Preferences', { selector: 'button' }));

    await waitFor(() => {
      expect(screen.getByText('Delivery Channels')).toBeInTheDocument();
    });
  });

  it('shows preference toggles', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Critical detection found');
    await user.click(screen.getByText('Preferences', { selector: 'button' }));

    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'In-app notifications' })).toBeInTheDocument();
    });
    expect(screen.getByRole('switch', { name: 'Email notifications' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Slack notifications' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Detection alerts' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'Sync alerts' })).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: 'System alerts' })).toBeInTheDocument();
  });

  it('shows severity filter select in preferences', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Critical detection found');
    await user.click(screen.getByText('Preferences', { selector: 'button' }));

    await waitFor(() => {
      expect(screen.getByLabelText('Minimum severity level')).toBeInTheDocument();
    });
  });

  it('shows save button disabled when no changes', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Critical detection found');
    await user.click(screen.getByText('Preferences', { selector: 'button' }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save preferences/i })).toBeDisabled();
    });
  });

  it('enables save button when toggle is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Critical detection found');
    await user.click(screen.getByText('Preferences', { selector: 'button' }));

    await waitFor(() => {
      expect(screen.getByRole('switch', { name: 'Email notifications' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('switch', { name: 'Email notifications' }));

    expect(screen.getByRole('button', { name: /save preferences/i })).toBeEnabled();
  });

  /* ------------------------------------------------------------------ */
  /*  Loading & error                                                     */
  /* ------------------------------------------------------------------ */

  it('shows loading state', () => {
    mockListNotifications.mockReturnValue(new Promise(() => {}));
    renderPage();

    expect(screen.getByText(/loading notifications/i)).toBeInTheDocument();
  });

  it('shows error state', async () => {
    mockListNotifications.mockRejectedValue(new Error('API error'));
    renderPage();

    expect(await screen.findByText(/failed to load notifications/i)).toBeInTheDocument();
  });
});
