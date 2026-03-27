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

  it('renders active users section', () => {
    renderWithProviders(<UsersPage />);

    expect(screen.getByRole('heading', { level: 2, name: /active users/i })).toBeInTheDocument();

    expect(screen.getByText('@jmassardo')).toBeInTheDocument();
    expect(screen.getByText('@mwestphal')).toBeInTheDocument();
    expect(screen.getByText('@skeshari')).toBeInTheDocument();
    expect(screen.getByText('@jdoe-bot')).toBeInTheDocument();
  });

  it('active user logins are clickable with clickableMention class', () => {
    renderWithProviders(<UsersPage />);

    const mentions = document.querySelectorAll('.clickableMention');
    // 4 active users + 1 granted-by mention in team mappings
    expect(mentions.length).toBeGreaterThanOrEqual(4);

    const jmassardoMention = screen.getByText('@jmassardo');
    expect(jmassardoMention.classList.contains('clickableMention')).toBe(true);
  });

  it('session counts are clickable with clickableSession class', () => {
    renderWithProviders(<UsersPage />);

    const sessions = document.querySelectorAll('.clickableSession');
    expect(sessions).toHaveLength(4);
  });

  it('clicking session count opens session detail modal', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);

    const sessions = document.querySelectorAll('.clickableSession');
    await user.click(sessions[0]);

    expect(await screen.findByText(/sessions — @jmassardo/i)).toBeInTheDocument();
  });

  it('session modal shows user info and note about API integration', async () => {
    const user = userEvent.setup();
    renderWithProviders(<UsersPage />);

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
});
