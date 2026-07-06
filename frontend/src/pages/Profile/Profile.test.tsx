import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { ProfilePage } from './index';

/* ─── Mock API module ──────────────────────────────────────────────────────── */

const mockGetUserProfile = vi.fn();
const mockGetUserPreferences = vi.fn();
const mockUpdateUserPreferences = vi.fn();
const mockGetUserSessions = vi.fn();
const mockRevokeSession = vi.fn();

vi.mock('../../api/userProfile', () => ({
  getUserProfile: (...args: unknown[]) => mockGetUserProfile(...args),
  getUserPreferences: (...args: unknown[]) => mockGetUserPreferences(...args),
  updateUserPreferences: (...args: unknown[]) => mockUpdateUserPreferences(...args),
  getUserSessions: (...args: unknown[]) => mockGetUserSessions(...args),
  revokeSession: (...args: unknown[]) => mockRevokeSession(...args),
}));

/* ─── Test data ────────────────────────────────────────────────────────────── */

const MOCK_PROFILE = {
  github_login: 'octocat',
  github_id: 1,
  display_name: 'Octocat',
  email: 'octocat@github.com',
  avatar_url: null,
  roles: ['analyst', 'viewer'],
  scoped_orgs: ['my-org'],
  scoped_repos: [],
  scope_type: 'scoped',
  login_history: [
    { timestamp: '2025-06-15T10:00:00Z', ip_address: '192.168.1.1' },
    { timestamp: '2025-06-14T08:30:00Z', ip_address: '10.0.0.1' },
  ],
  session_expires_at: '2025-12-31T23:59:59Z',
};

const MOCK_PREFERENCES = {
  theme: 'system' as const,
  default_dashboard_view: 'operations' as const,
  default_org: '',
  timezone: 'UTC',
  date_format: 'relative' as const,
  items_per_page: 25,
};

const MOCK_SESSIONS = {
  sessions: [
    {
      session_id: 'abc12345-1111-2222-3333-444444444444',
      ip_address: '192.168.1.1',
      user_agent: 'Mozilla/5.0',
      created_at: '2025-06-15T10:00:00Z',
      expires_at: '2025-06-16T10:00:00Z',
      is_current: true,
    },
    {
      session_id: 'def67890-5555-6666-7777-888888888888',
      ip_address: '10.0.0.1',
      user_agent: 'Chrome/125',
      created_at: '2025-06-14T08:00:00Z',
      expires_at: '2025-06-15T08:00:00Z',
      is_current: false,
    },
  ],
};

/* ─── Helpers ──────────────────────────────────────────────────────────────── */

function renderProfile(route = '/profile/profile') {
  return renderWithProviders(<ProfilePage />, {
    route,
    routePath: '/profile/:tab',
  });
}

/* ─── Tests ────────────────────────────────────────────────────────────────── */

describe('ProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetUserProfile.mockResolvedValue(MOCK_PROFILE);
    mockGetUserPreferences.mockResolvedValue(MOCK_PREFERENCES);
    mockGetUserSessions.mockResolvedValue(MOCK_SESSIONS);
    mockUpdateUserPreferences.mockImplementation((prefs) => Promise.resolve(prefs));
    mockRevokeSession.mockResolvedValue(undefined);
  });

  /* ─── Profile Tab ──────────────────────────────────────────────────────── */

  it('renders the page header and tabs', async () => {
    renderProfile();

    expect(screen.getByText('Profile & Preferences')).toBeInTheDocument();

    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(3);
    expect(screen.getByRole('tab', { name: 'Profile' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Preferences' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Sessions' })).toBeInTheDocument();
  });

  it('displays user profile information on the Profile tab', async () => {
    renderProfile();

    await waitFor(() => {
      expect(screen.getByText('Octocat')).toBeInTheDocument();
    });

    expect(screen.getByText('@octocat')).toBeInTheDocument();
    expect(screen.getByText('octocat@github.com')).toBeInTheDocument();
  });

  it('displays role badges', async () => {
    renderProfile();

    await waitFor(() => {
      expect(screen.getByText('Analyst')).toBeInTheDocument();
    });
    expect(screen.getByText('Viewer')).toBeInTheDocument();
  });

  it('displays login history table', async () => {
    renderProfile();

    await waitFor(() => {
      expect(screen.getByText('Login History')).toBeInTheDocument();
    });

    expect(screen.getByText('192.168.1.1')).toBeInTheDocument();
    expect(screen.getByText('10.0.0.1')).toBeInTheDocument();
  });

  it('shows empty state when no login history', async () => {
    mockGetUserProfile.mockResolvedValue({
      ...MOCK_PROFILE,
      login_history: [],
    });

    renderProfile();

    await waitFor(() => {
      expect(screen.getByText('No login history available.')).toBeInTheDocument();
    });
  });

  it('shows error state when profile fails to load', async () => {
    mockGetUserProfile.mockRejectedValue(new Error('Network error'));

    renderProfile();

    await waitFor(() => {
      expect(screen.getByText('Failed to load profile.')).toBeInTheDocument();
    });
  });

  /* ─── Preferences Tab ──────────────────────────────────────────────────── */

  it('switches to Preferences tab and shows preference form', async () => {
    const user = userEvent.setup();
    renderProfile();

    const prefsTab = screen.getByRole('tab', { name: 'Preferences' });
    await user.click(prefsTab);

    await waitFor(() => {
      expect(screen.getByLabelText('Theme')).toBeInTheDocument();
    });

    expect(screen.getByLabelText('Default Dashboard View')).toBeInTheDocument();
    expect(screen.getByLabelText('Default Organization')).toBeInTheDocument();
    expect(screen.getByLabelText('Timezone')).toBeInTheDocument();
    expect(screen.getByLabelText('Date Format')).toBeInTheDocument();
    expect(screen.getByLabelText('Items Per Page')).toBeInTheDocument();
  });

  it('updates preferences and shows success message', async () => {
    const user = userEvent.setup();
    renderProfile();

    await user.click(screen.getByRole('tab', { name: 'Preferences' }));

    await waitFor(() => {
      expect(screen.getByLabelText('Theme')).toBeInTheDocument();
    });

    const themeSelect = screen.getByLabelText('Theme');
    await user.selectOptions(themeSelect, 'dark');

    const saveButton = screen.getByRole('button', { name: 'Save Preferences' });
    await user.click(saveButton);

    await waitFor(() => {
      expect(mockUpdateUserPreferences).toHaveBeenCalledWith(
        expect.objectContaining({ theme: 'dark' }),
        expect.anything(),
      );
    });

    await waitFor(() => {
      expect(screen.getByText('Preferences saved successfully.')).toBeInTheDocument();
    });
  });

  it('shows error message when preferences save fails', async () => {
    mockUpdateUserPreferences.mockRejectedValue(new Error('Save failed'));
    const user = userEvent.setup();
    renderProfile();

    await user.click(screen.getByRole('tab', { name: 'Preferences' }));

    await waitFor(() => {
      expect(screen.getByLabelText('Theme')).toBeInTheDocument();
    });

    // Change a value to enable Save button
    await user.selectOptions(screen.getByLabelText('Theme'), 'light');
    await user.click(screen.getByRole('button', { name: 'Save Preferences' }));

    await waitFor(() => {
      expect(screen.getByText('Failed to save preferences.')).toBeInTheDocument();
    });
  });

  /* ─── Sessions Tab ─────────────────────────────────────────────────────── */

  it('switches to Sessions tab and shows active sessions', async () => {
    const user = userEvent.setup();
    renderProfile();

    await user.click(screen.getByRole('tab', { name: 'Sessions' }));

    await waitFor(() => {
      expect(screen.getByText('Active Sessions')).toBeInTheDocument();
    });

    // Current session badge
    expect(screen.getByText('Current')).toBeInTheDocument();

    // Should show a Revoke button for the non-current session
    const revokeButtons = screen.getAllByRole('button', { name: 'Revoke' });
    expect(revokeButtons).toHaveLength(1);
  });

  it('revokes a non-current session', async () => {
    const user = userEvent.setup();
    renderProfile();

    await user.click(screen.getByRole('tab', { name: 'Sessions' }));

    await waitFor(() => {
      expect(screen.getByText('Active Sessions')).toBeInTheDocument();
    });

    const revokeButton = screen.getByRole('button', { name: 'Revoke' });
    await user.click(revokeButton);

    await waitFor(() => {
      expect(mockRevokeSession).toHaveBeenCalledWith(
        'def67890-5555-6666-7777-888888888888',
        expect.anything(),
      );
    });
  });

  it('shows error when session revocation fails', async () => {
    mockRevokeSession.mockRejectedValue(new Error('Revoke failed'));
    const user = userEvent.setup();
    renderProfile();

    await user.click(screen.getByRole('tab', { name: 'Sessions' }));

    await waitFor(() => {
      expect(screen.getByText('Active Sessions')).toBeInTheDocument();
    });

    const revokeButton = screen.getByRole('button', { name: 'Revoke' });
    await user.click(revokeButton);

    await waitFor(() => {
      expect(screen.getByText('Failed to revoke session.')).toBeInTheDocument();
    });
  });

  it('shows empty sessions state', async () => {
    mockGetUserSessions.mockResolvedValue({ sessions: [] });
    const user = userEvent.setup();
    renderProfile();

    await user.click(screen.getByRole('tab', { name: 'Sessions' }));

    await waitFor(() => {
      expect(screen.getByText('No active sessions found.')).toBeInTheDocument();
    });
  });

  it('shows no roles assigned message when user has no roles', async () => {
    mockGetUserProfile.mockResolvedValue({
      ...MOCK_PROFILE,
      roles: [],
    });

    renderProfile();

    await waitFor(() => {
      expect(screen.getByText('No roles assigned')).toBeInTheDocument();
    });
  });
});
