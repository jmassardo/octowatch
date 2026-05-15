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

const TWO_ORGS_USER = {
  github_login: 'jane-doe',
  github_id: 42,
  roles: ['admin'],
  scoped_orgs: ['my-org', 'other-org'],
  scoped_repos: [],
  scope_type: 'all',
  session_expires_at: '2025-12-31T00:00:00Z',
} as const;

const SINGLE_ORG_USER = {
  ...TWO_ORGS_USER,
  scoped_orgs: ['my-org'],
} as const;

const MANY_ORGS_USER = {
  ...TWO_ORGS_USER,
  scoped_orgs: ['org-1', 'org-2', 'org-3', 'org-4', 'org-5', 'org-6', 'org-7'],
} as const;

function renderTopBar(
  props: { onShowTour?: () => void; onToggleSidebar?: () => void; sidebarOpen?: boolean } = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <TopBar {...props} />
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
      data: TWO_ORGS_USER,
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

  it('renders a mobile navigation toggle with state when provided', () => {
    renderTopBar({ onToggleSidebar: vi.fn(), sidebarOpen: true });
    expect(screen.getByRole('button', { name: /close navigation menu/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  it('renders dropdown for multiple orgs with all options', async () => {
    const user = userEvent.setup();
    renderTopBar();

    const trigger = screen.getByLabelText('Select organization');
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveTextContent('All organizations');

    await user.click(trigger);
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(3);
    expect(options[0]).toHaveTextContent('All organizations');
    expect(options[1]).toHaveTextContent('my-org');
    expect(options[2]).toHaveTextContent('other-org');
  });

  it('marks "All organizations" as selected when no org is selected', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    const allOption = screen.getByRole('option', { name: /All organizations/ });
    expect(allOption).toHaveAttribute('aria-selected', 'true');
  });

  it('marks correct option as selected when an org is selected', async () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg });
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    const myOrgOption = screen.getByRole('option', { name: 'my-org' });
    expect(myOrgOption).toHaveAttribute('aria-selected', 'true');
    const allOption = screen.getByRole('option', { name: /All organizations/ });
    expect(allOption).toHaveAttribute('aria-selected', 'false');
  });

  it('selects org when option is clicked', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    await user.click(screen.getByRole('option', { name: 'other-org' }));
    expect(setSelectedOrg).toHaveBeenCalledWith('other-org');
  });

  it('selects "All" when All organizations option is clicked', async () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg });
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    await user.click(screen.getByRole('option', { name: /All organizations/ }));
    expect(setSelectedOrg).toHaveBeenCalledWith('');
  });

  it('renders single org as dropdown (not tabs)', () => {
    mockUseCurrentUser.mockReturnValue({
      data: SINGLE_ORG_USER,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    renderTopBar();
    expect(screen.getByLabelText('Select organization')).toBeInTheDocument();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  });

  it('shows "No organizations" label when user has no scoped_orgs', () => {
    mockUseCurrentUser.mockReturnValue({
      data: { ...TWO_ORGS_USER, scoped_orgs: [] },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    renderTopBar();
    expect(screen.getByTestId('org-label')).toHaveTextContent('No organizations');
  });

  it('shows "No organizations" when user data is not yet loaded', () => {
    mockUseCurrentUser.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    renderTopBar();
    expect(screen.getByTestId('org-label')).toHaveTextContent('No organizations');
  });

  it('renders dropdown for >6 orgs', async () => {
    mockUseCurrentUser.mockReturnValue({
      data: MANY_ORGS_USER,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    const user = userEvent.setup();
    renderTopBar();

    const trigger = screen.getByLabelText('Select organization');
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveTextContent('All organizations');

    await user.click(trigger);
    expect(screen.getByLabelText('Filter organizations')).toBeInTheDocument();
  });

  it('filters orgs in dropdown when typing', async () => {
    mockUseCurrentUser.mockReturnValue({
      data: MANY_ORGS_USER,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    await user.type(screen.getByLabelText('Filter organizations'), 'org-1');

    expect(screen.getByRole('option', { name: 'org-1' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'org-3' })).not.toBeInTheDocument();
  });

  it('announces when no organizations match the filter', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    await user.type(screen.getByLabelText('Filter organizations'), 'missing-org');

    expect(screen.getByRole('status')).toHaveTextContent(/no organizations match your filter/i);
  });

  it('selects org from dropdown and closes it', async () => {
    mockUseCurrentUser.mockReturnValue({
      data: MANY_ORGS_USER,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    await user.click(screen.getByRole('option', { name: 'org-3' }));

    expect(setSelectedOrg).toHaveBeenCalledWith('org-3');
    expect(screen.queryByLabelText('Filter organizations')).not.toBeInTheDocument();
  });

  it('closes dropdown when clicking outside', async () => {
    mockUseCurrentUser.mockReturnValue({
      data: MANY_ORGS_USER,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByLabelText('Select organization'));
    expect(screen.getByLabelText('Filter organizations')).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByLabelText('Filter organizations')).not.toBeInTheDocument();
  });

  it('renders the org dropdown trigger with proper aria attributes', () => {
    renderTopBar();
    const trigger = screen.getByLabelText('Select organization');
    expect(trigger).toBeInTheDocument();
    expect(trigger).toHaveAttribute('aria-haspopup', 'listbox');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('renders the new report button with an accessible name', () => {
    renderTopBar();
    expect(screen.getByRole('button', { name: /create new report/i })).toBeInTheDocument();
  });

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

  it('renders user avatar button when user is loaded', () => {
    renderTopBar();
    expect(screen.getByLabelText('User menu')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'User menu' })).toHaveAttribute(
      'aria-haspopup',
      'menu',
    );
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

    expect(screen.getByRole('menu', { name: /user actions/i })).toBeInTheDocument();
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
      data: { ...TWO_ORGS_USER, roles: [] },
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
