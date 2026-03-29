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

  // ----- Org tabs (multiple orgs, ≤6) -----

  it('renders segmented tabs for multiple orgs', () => {
    renderTopBar();
    const tablist = screen.getByRole('tablist');
    expect(tablist).toBeInTheDocument();

    const tabs = screen.getAllByRole('tab');
    // "All" + 2 org tabs
    expect(tabs).toHaveLength(3);
    expect(tabs[0]).toHaveTextContent('All');
    expect(tabs[1]).toHaveTextContent('my-org');
    expect(tabs[2]).toHaveTextContent('other-org');
  });

  it('marks "All" tab as selected when no org is selected', () => {
    renderTopBar();
    const allTab = screen.getByRole('tab', { name: 'All' });
    expect(allTab).toHaveAttribute('aria-selected', 'true');
  });

  it('marks correct tab as selected when an org is selected', () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg });
    renderTopBar();
    const myOrgTab = screen.getByRole('tab', { name: 'my-org' });
    expect(myOrgTab).toHaveAttribute('aria-selected', 'true');
    const allTab = screen.getByRole('tab', { name: 'All' });
    expect(allTab).toHaveAttribute('aria-selected', 'false');
  });

  it('selects org when tab is clicked', async () => {
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByRole('tab', { name: 'other-org' }));
    expect(setSelectedOrg).toHaveBeenCalledWith('other-org');
  });

  it('selects "All" when All tab is clicked', async () => {
    mockUseOrg.mockReturnValue({ selectedOrg: 'my-org', setSelectedOrg });
    const user = userEvent.setup();
    renderTopBar();

    await user.click(screen.getByRole('tab', { name: 'All' }));
    expect(setSelectedOrg).toHaveBeenCalledWith('');
  });

  // ----- Single org label -----

  it('renders single org as a label (not tabs)', () => {
    mockUseCurrentUser.mockReturnValue({
      data: SINGLE_ORG_USER,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCurrentUser>);

    renderTopBar();
    expect(screen.getByTestId('org-label')).toHaveTextContent('my-org');
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  });

  // ----- No orgs label -----

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

  // ----- Dropdown for many orgs (>6) -----

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

  // ----- Add org button -----

  it('renders the "Add org" button', () => {
    renderTopBar();
    expect(screen.getByLabelText('Add organization')).toBeInTheDocument();
    expect(screen.getByText('Add org')).toBeInTheDocument();
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
