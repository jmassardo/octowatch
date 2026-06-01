import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { PermissionGate } from './PermissionGate';

import * as usePermissionsModule from '../../hooks/usePermissions';

vi.mock('../../hooks/usePermissions');

const mockedUsePermissions = vi.mocked(usePermissionsModule.usePermissions);

function renderWithProviders(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('PermissionGate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders children when user has permission', () => {
    mockedUsePermissions.mockReturnValue({
      permissions: ['events:view'],
      roles: ['viewer'],
      isLoading: false,
      hasPermission: (r: string, a: string) => `${r}:${a}` === 'events:view',
      hasAnyPermission: () => true,
      hasRole: () => true,
      scopedOrgs: [],
      scopedRepos: [],
      scopeType: 'global',
      isOrgInScope: () => true,
      isRepoInScope: () => true,
      canEdit: () => false,
    });

    renderWithProviders(
      <PermissionGate resource="events" action="view">
        <span>Visible content</span>
      </PermissionGate>,
    );

    expect(screen.getByText('Visible content')).toBeInTheDocument();
  });

  it('renders fallback when user lacks permission', () => {
    mockedUsePermissions.mockReturnValue({
      permissions: ['events:view'],
      roles: ['viewer'],
      isLoading: false,
      hasPermission: (r: string, a: string) => `${r}:${a}` === 'events:view',
      hasAnyPermission: () => false,
      hasRole: () => false,
      scopedOrgs: [],
      scopedRepos: [],
      scopeType: 'global',
      isOrgInScope: () => true,
      isRepoInScope: () => true,
      canEdit: () => false,
    });

    renderWithProviders(
      <PermissionGate resource="admin_users" action="view" fallback={<span>No access</span>}>
        <span>Admin content</span>
      </PermissionGate>,
    );

    expect(screen.queryByText('Admin content')).not.toBeInTheDocument();
    expect(screen.getByText('No access')).toBeInTheDocument();
  });

  it('renders nothing when no fallback and no permission', () => {
    mockedUsePermissions.mockReturnValue({
      permissions: [],
      roles: [],
      isLoading: false,
      hasPermission: () => false,
      hasAnyPermission: () => false,
      hasRole: () => false,
      scopedOrgs: [],
      scopedRepos: [],
      scopeType: 'global',
      isOrgInScope: () => true,
      isRepoInScope: () => true,
      canEdit: () => false,
    });

    const { container } = renderWithProviders(
      <PermissionGate resource="events" action="view">
        <span>Content</span>
      </PermissionGate>,
    );

    expect(screen.queryByText('Content')).not.toBeInTheDocument();
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when loading', () => {
    mockedUsePermissions.mockReturnValue({
      permissions: [],
      roles: [],
      isLoading: true,
      hasPermission: () => false,
      hasAnyPermission: () => false,
      hasRole: () => false,
      scopedOrgs: [],
      scopedRepos: [],
      scopeType: 'global',
      isOrgInScope: () => true,
      isRepoInScope: () => true,
      canEdit: () => false,
    });

    const { container } = renderWithProviders(
      <PermissionGate resource="events" action="view">
        <span>Content</span>
      </PermissionGate>,
    );

    expect(container.innerHTML).toBe('');
  });
});
