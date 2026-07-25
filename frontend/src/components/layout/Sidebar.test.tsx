import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Sidebar } from './Sidebar';

vi.mock('../../api/detections', () => ({
  listDetections: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 1 }),
}));
vi.mock('../../api/healthSignals', () => ({
  getHealthSummary: vi.fn().mockResolvedValue({
    stale_repos: 0,
    pat_no_expiry: 0,
    pat_stale: 0,
    bypass_offenders: 0,
    ext_collab_elevated: 0,
  }),
}));
vi.mock('../../hooks/useFeatures', () => ({
  useFeatures: () => ({
    features: {
      velocity: true,
      dev_activity: true,
      copilot_insights: true,
      org_health: true,
    },
    loading: false,
  }),
}));
vi.mock('../../hooks/usePermissions', () => ({
  usePermissions: () => ({
    permissions: ['*:*'],
    roles: ['super_admin'],
    isLoading: false,
    hasPermission: () => true,
    hasAnyPermission: () => true,
    hasRole: () => true,
    scopedOrgs: [],
    scopedRepos: [],
    scopeType: 'global',
    isOrgInScope: () => true,
    isRepoInScope: () => true,
    canEdit: () => true,
  }),
}));

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderSidebar(
  props: { mobileOpen?: boolean; onMobileClose?: () => void } = {},
  initialEntries = ['/'],
) {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={initialEntries}>
        <Sidebar {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Sidebar', () => {
  it('renders main navigation with aria-label', () => {
    renderSidebar();
    expect(screen.getByRole('navigation', { name: /main navigation/i })).toBeInTheDocument();
  });

  it('marks the active item with aria-current', () => {
    renderSidebar({}, ['/dashboard']);
    expect(screen.getByRole('link', { name: /dashboard/i })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('renders nav links for all sections', () => {
    renderSidebar();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Threat Detections')).toBeInTheDocument();
    expect(screen.getByText('Events Explorer')).toBeInTheDocument();
    expect(screen.getByText('Query Explorer')).toBeInTheDocument();
    expect(screen.getAllByText('Settings').length).toBeGreaterThanOrEqual(1);
  });

  it('shows close button when in mobile mode', () => {
    const onClose = vi.fn();
    renderSidebar({ mobileOpen: true, onMobileClose: onClose });
    expect(screen.getByRole('button', { name: /close navigation/i })).toBeInTheDocument();
  });

  it('does not show close button when not in mobile mode', () => {
    renderSidebar();
    expect(screen.queryByRole('button', { name: /close navigation/i })).not.toBeInTheDocument();
  });

  it('calls onMobileClose when close button is clicked', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderSidebar({ mobileOpen: true, onMobileClose: onClose });

    await user.click(screen.getByRole('button', { name: /close navigation/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('renders backdrop when mobile sidebar is open', () => {
    const onClose = vi.fn();
    renderSidebar({ mobileOpen: true, onMobileClose: onClose });
    expect(screen.getByTestId('sidebar-backdrop')).toBeInTheDocument();
  });

  it('does not render backdrop when mobile sidebar is closed', () => {
    const onClose = vi.fn();
    renderSidebar({ mobileOpen: false, onMobileClose: onClose });
    expect(screen.queryByTestId('sidebar-backdrop')).not.toBeInTheDocument();
  });

  it('calls onMobileClose when backdrop is clicked', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderSidebar({ mobileOpen: true, onMobileClose: onClose });

    await user.click(screen.getByTestId('sidebar-backdrop'));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
