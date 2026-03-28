import { describe, it, expect, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test/utils';
import { UsersPage } from './index';

vi.mock('../../api/admin', () => ({
  listRoleAssignments: vi.fn().mockResolvedValue([
    {
      id: 1,
      role_id: 1,
      github_login: 'secops-admin',
      github_team_slug: 'security-team',
      scope_type: 'admin',
      scope_value: null,
      granted_by: 'jmassardo',
      granted_at: new Date().toISOString(),
    },
  ]),
  createRoleAssignment: vi.fn().mockResolvedValue({}),
  deleteRoleAssignment: vi.fn().mockResolvedValue(undefined),
  listRoles: vi.fn().mockResolvedValue([
    { name: 'viewer' },
    { name: 'analyst' },
    { name: 'admin' },
  ]),
  getActiveSessions: vi.fn().mockResolvedValue([
    {
      login: 'jmassardo',
      last_active_at: new Date().toISOString(),
      session_count: 3,
      role: 'sys_admin',
      mfa_enabled: true,
    },
    {
      login: 'mwestphal',
      last_active_at: new Date(Date.now() - 12 * 60_000).toISOString(),
      session_count: 1,
      role: 'analyst',
      mfa_enabled: true,
    },
    {
      login: 'skeshari',
      last_active_at: new Date(Date.now() - 34 * 60_000).toISOString(),
      session_count: 2,
      role: 'analyst',
      mfa_enabled: false,
    },
    {
      login: 'jdoe-bot',
      last_active_at: new Date(Date.now() - 60 * 60_000).toISOString(),
      session_count: 1,
      role: 'viewer',
      mfa_enabled: true,
    },
  ]),
}));

describe('UsersPage', () => {
  it('renders page title and subtitle', () => {
    renderWithProviders(<UsersPage />);

    expect(screen.getByRole('heading', { level: 1, name: /users & roles/i })).toBeInTheDocument();
    expect(screen.getByText(/manage team mappings and active user sessions/i)).toBeInTheDocument();
  });

  it('renders team mappings section', async () => {
    renderWithProviders(<UsersPage />);

    expect(screen.getByRole('heading', { level: 2, name: /team mappings/i })).toBeInTheDocument();

    // Wait for team mapping data to load
    expect(await screen.findByText('@security-team')).toBeInTheDocument();
  });

  it('renders active users section from API data', async () => {
    renderWithProviders(<UsersPage />);

    expect(screen.getByRole('heading', { level: 2, name: /active users/i })).toBeInTheDocument();

    // Wait for session data to load from API - use findAllByText because
    // @jmassardo also appears in team mappings granted_by column
    const jmassardoElements = await screen.findAllByText('@jmassardo');
    expect(jmassardoElements.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText('@mwestphal')).toBeInTheDocument();
    expect(await screen.findByText('@skeshari')).toBeInTheDocument();
    expect(await screen.findByText('@jdoe-bot')).toBeInTheDocument();
  });

  it('active user logins are clickable with clickableMention class', async () => {
    renderWithProviders(<UsersPage />);

    // Wait for sessions to load (use unique login to avoid multi-match)
    await screen.findByText('@mwestphal');

    const mentions = document.querySelectorAll('.clickableMention');
    // 4 active users + 1 granted-by mention in team mappings
    expect(mentions.length).toBeGreaterThanOrEqual(4);

    const jmassardoMention = screen.getAllByText('@jmassardo')[0];
    expect(jmassardoMention.classList.contains('clickableMention')).toBe(true);
  });

  it('session counts are clickable with clickableSession class', async () => {
    renderWithProviders(<UsersPage />);

    // Wait for sessions to load
    await screen.findByText('@mwestphal');

    const sessions = document.querySelectorAll('.clickableSession');
    expect(sessions).toHaveLength(4);
  });

  it('clicking session count opens session detail modal', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);

    // Wait for sessions to load
    await screen.findByText('@mwestphal');

    const sessions = document.querySelectorAll('.clickableSession');
    await user.click(sessions[0]);

    expect(await screen.findByText(/sessions — @jmassardo/i)).toBeInTheDocument();
  });

  it('session modal shows user info and note about API integration', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);

    // Wait for sessions to load
    await screen.findByText('@mwestphal');

    const sessions = document.querySelectorAll('.clickableSession');
    await user.click(sessions[0]);

    const modalTitle = await screen.findByText(/sessions — @jmassardo/i);
    const modal = modalTitle.closest('.dialog')!;

    expect(within(modal as HTMLElement).getByText('Active sessions')).toBeInTheDocument();
    expect(within(modal as HTMLElement).getByText(/requires GitHub API integration/i)).toBeInTheDocument();
  });

  it('granted-by mentions are clickable with clickableMention class', async () => {
    renderWithProviders(<UsersPage />);

    // Wait for the team mapping data to load
    await screen.findByText('@security-team');

    // The granted-by @jmassardo in the team mappings table
    const grantedByMention = screen.getAllByText('@jmassardo').find(
      (el) => el.closest('table')?.querySelector('th')?.textContent === 'GitHub team',
    );
    expect(grantedByMention).toBeDefined();
    expect(grantedByMention!.classList.contains('clickableMention')).toBe(true);
  });

  it('shows empty state when no active sessions', async () => {
    const { getActiveSessions } = await import('../../api/admin');
    vi.mocked(getActiveSessions).mockResolvedValueOnce([]);

    renderWithProviders(<UsersPage />);

    expect(await screen.findByText('No active sessions in the last 24 hours')).toBeInTheDocument();
  });
});
