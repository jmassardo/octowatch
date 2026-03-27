import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TopBar } from './TopBar';

vi.mock('../../hooks/useOrg');
vi.mock('../../hooks/useCurrentUser');
vi.mock('../../hooks/useTheme');
vi.mock('../../api/auth');

import { useOrg } from '../../hooks/useOrg';
import { useCurrentUser } from '../../hooks/useCurrentUser';
import { useTheme } from '../../hooks/useTheme';
import { logout } from '../../api/auth';

const mockUseOrg = vi.mocked(useOrg);
const mockUseCurrentUser = vi.mocked(useCurrentUser);
const mockUseTheme = vi.mocked(useTheme);
const mockLogout = vi.mocked(logout);

const DEFAULT_USER = {
  github_login: 'jane-doe',
  github_id: 42,
  roles: ['admin'],
  scoped_orgs: ['my-org', 'other-org'],
  scoped_repos: [],
  scope_type: 'all',
  session_expires_at: '2025-12-31T00:00:00Z',
} as const;

function renderTopBar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <TopBar />
    </QueryClientProvider>,
  );
}

describe('TopBar', () => {
  const setSelectedOrg = vi.fn();
  const toggleTheme = vi.fn();
  const setTheme = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();

    mockUseOrg.mockReturnValue({ selectedOrg: '', setSelectedOrg });

    mockUseCurrentUser.mockReturnValue({
      data: DEFAULT_USER,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    mockUseTheme.mockReturnValue({ theme: 'system', toggleTheme, setTheme });

    mockLogout.mockResolvedValue(undefined);
  });

  it('renders as a banner landmark', () => {
    renderTopBar();
    expect(screen.getByRole('banner')).toBeInTheDocument();
  });

  // ----- Org tabs -----

  it('renders user scoped_orgs as tab buttons', () => {
    renderTopBar();
    expect(screen.getByText('my-org')).toBeInTheDocument();
    expect(screen.getByText('other-org')).toBeInTheDocument();
  });

  it('renders fallback orgs when user has empty scoped_orgs', () => {
    mockUseCurrentUser.mockReturnValue({
      data: { ...DEFAULT_USER, scoped_orgs: [] },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    renderTopBar();
    expect(screen.getByText('acme-corp')).toBeInTheDocument();
    expect(screen.getByText('globex')).toBeInTheDocument();
  });

  it('renders fallback orgs when user data is not yet loaded', () => {
    mockUseCurrentUser.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    renderTopBar();
    expect(screen.getByText('acme-corp')).toBeInTheDocument();
    expect(screen.getByText('globex')).toBeInTheDocument();
  });

  it('applies active class only to the selected org tab', () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg });

    renderTopBar();
    expect(screen.getByText('my-org').className).toContain('active');
    expect(screen.getByText('other-org').className).not.toContain('active');
  });

  it('calls setSelectedOrg when an org tab is clicked', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByText('other-org'));
    expect(setSelectedOrg).toHaveBeenCalledWith('other-org');
  });

  // ----- "+ Add org" tab -----

  it('always renders the "+ Add org" tab', () => {
    renderTopBar();
    const addBtn = screen.getByText('+ Add org');
    expect(addBtn).toBeInTheDocument();
    expect(addBtn).toHaveAttribute('aria-label', 'Add organization');
  });

  it('applies add class to the "+ Add org" tab', () => {
    renderTopBar();
    expect(screen.getByText('+ Add org').className).toContain('add');
  });

  it('renders "+ Add org" as the last tab (after org tabs)', () => {
    renderTopBar();
    const tabs = screen.getAllByRole('button').filter((btn) =>
      btn.className.includes('orgTab'),
    );
    const lastTab = tabs[tabs.length - 1];
    expect(lastTab).toHaveTextContent('+ Add org');
  });

  // ----- "New report" button -----

  it('renders the "New report" button', () => {
    renderTopBar();
    expect(screen.getByText('New report')).toBeInTheDocument();
  });

  // ----- Theme toggle -----

  it('renders the theme toggle button with system label by default', () => {
    renderTopBar();
    expect(screen.getByLabelText(/Theme: System/)).toBeInTheDocument();
  });

  it('calls toggleTheme when the theme button is clicked', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText(/Theme: System/));
    expect(toggleTheme).toHaveBeenCalledOnce();
  });

  it('shows light label when theme is light', () => {
    mockUseTheme.mockReturnValue({ theme: 'light', toggleTheme, setTheme });
    renderTopBar();
    expect(screen.getByLabelText(/Theme: Light/)).toBeInTheDocument();
  });

  it('shows dark label when theme is dark', () => {
    mockUseTheme.mockReturnValue({ theme: 'dark', toggleTheme, setTheme });
    renderTopBar();
    expect(screen.getByLabelText(/Theme: Dark/)).toBeInTheDocument();
  });

  // ----- User avatar & menu -----

  it('renders user avatar button when user is loaded', () => {
    renderTopBar();
    expect(screen.getByLabelText('User menu')).toBeInTheDocument();
  });

  it('does not render user avatar when user data is unavailable', () => {
    mockUseCurrentUser.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    renderTopBar();
    expect(screen.queryByLabelText('User menu')).not.toBeInTheDocument();
  });

  it('opens the dropdown menu when avatar is clicked', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('User menu'));

    expect(screen.getByText('@jane-doe')).toBeInTheDocument();
    expect(screen.getByText('admin')).toBeInTheDocument();
    expect(screen.getByText('Sign out')).toBeInTheDocument();
  });

  it('closes the menu when avatar is clicked again', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('User menu'));
    expect(screen.getByText('Sign out')).toBeInTheDocument();

    await user.click(screen.getByLabelText('User menu'));
    expect(screen.queryByText('Sign out')).not.toBeInTheDocument();
  });

  it('calls logout when "Sign out" is clicked', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('User menu'));
    await user.click(screen.getByText('Sign out'));

    expect(mockLogout).toHaveBeenCalledOnce();
  });

  it('does not show role in menu when user has no roles', async () => {
    mockUseCurrentUser.mockReturnValue({
      data: { ...DEFAULT_USER, roles: [] },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('User menu'));
    expect(screen.getByText('@jane-doe')).toBeInTheDocument();
    expect(screen.queryByText('admin')).not.toBeInTheDocument();
  });
});
