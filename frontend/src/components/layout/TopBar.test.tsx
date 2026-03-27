import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
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
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>
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

  // ----- Org dropdown -----

  it('renders dropdown trigger with "All organizations" when no org selected', () => {
    renderTopBar();
    const trigger = screen.getByLabelText('Select organization');
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveTextContent('All organizations');
  });

  it('renders dropdown trigger with selected org name', () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg });
    renderTopBar();
    const trigger = screen.getByLabelText('Select organization');
    expect(trigger).toHaveTextContent('my-org');
  });

  it('opens dropdown on click and shows filter input', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));

    expect(screen.getByLabelText('Filter organizations')).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText('Filter organizations...'),
    ).toBeInTheDocument();
  });

  it('shows all orgs in the dropdown', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));

    expect(
      screen.getByRole('option', { name: /All organizations/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('option', { name: 'my-org' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('option', { name: 'other-org' }),
    ).toBeInTheDocument();
  });

  it('filters orgs when typing in search', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    await user.type(screen.getByLabelText('Filter organizations'), 'my');

    expect(
      screen.getByRole('option', { name: 'my-org' }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('option', { name: 'other-org' }),
    ).not.toBeInTheDocument();
    // "All organizations" stays visible
    expect(
      screen.getByRole('option', { name: /All organizations/ }),
    ).toBeInTheDocument();
  });

  it('selects org on click and closes dropdown', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    await user.click(screen.getByRole('option', { name: 'my-org' }));

    expect(setSelectedOrg).toHaveBeenCalledWith('my-org');
    expect(
      screen.queryByLabelText('Filter organizations'),
    ).not.toBeInTheDocument();
  });

  it('selects "All organizations" and closes dropdown', async () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg });
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    await user.click(
      screen.getByRole('option', { name: /All organizations/ }),
    );

    expect(setSelectedOrg).toHaveBeenCalledWith('');
    expect(
      screen.queryByLabelText('Filter organizations'),
    ).not.toBeInTheDocument();
  });

  it('closes dropdown when clicking outside', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    expect(screen.getByLabelText('Filter organizations')).toBeInTheDocument();

    fireEvent.mouseDown(document.body);

    expect(
      screen.queryByLabelText('Filter organizations'),
    ).not.toBeInTheDocument();
  });

  it('shows "No organizations" when user has no scoped_orgs', async () => {
    mockUseCurrentUser.mockReturnValue({
      data: { ...DEFAULT_USER, scoped_orgs: [] },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    expect(screen.getByText('No organizations')).toBeInTheDocument();
  });

  it('shows "No organizations" when user data is not yet loaded', async () => {
    mockUseCurrentUser.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    expect(screen.getByText('No organizations')).toBeInTheDocument();
  });

  it('shows checkmark on selected org', async () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg });
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));

    const myOrgOption = screen.getByRole('option', { name: 'my-org' });
    expect(myOrgOption).toHaveTextContent('✓');

    const otherOrgOption = screen.getByRole('option', { name: 'other-org' });
    expect(otherOrgOption).not.toHaveTextContent('✓');
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
