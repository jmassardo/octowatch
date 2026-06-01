import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { EditPermissionGate } from './EditPermissionGate';
import * as usePermissionsModule from '../../hooks/usePermissions';

vi.mock('../../hooks/usePermissions');
const mockedUsePermissions = vi.mocked(usePermissionsModule.usePermissions);

function renderWithProviders(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('EditPermissionGate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders children normally when user has edit permission', () => {
    mockedUsePermissions.mockReturnValue({
      permissions: ['posture:edit'],
      roles: ['security_engineer'],
      isLoading: false,
      hasPermission: (r: string, a: string) => `${r}:${a}` === 'posture:edit',
      hasAnyPermission: () => true,
      hasRole: () => true,
      scopedOrgs: [],
      scopedRepos: [],
      scopeType: 'global',
      isOrgInScope: () => true,
      isRepoInScope: () => true,
      canEdit: (resource: string) => resource === 'posture',
    });

    renderWithProviders(
      <EditPermissionGate resource="posture">
        <button>Save Changes</button>
      </EditPermissionGate>,
    );

    const button = screen.getByRole('button', { name: 'Save Changes' });
    expect(button).toBeInTheDocument();
    expect(button.closest('[aria-disabled="true"]')).toBeNull();
  });

  it('renders children in disabled wrapper when user lacks edit permission', () => {
    mockedUsePermissions.mockReturnValue({
      permissions: ['posture:view'],
      roles: ['viewer'],
      isLoading: false,
      hasPermission: (r: string, a: string) => `${r}:${a}` === 'posture:view',
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
      <EditPermissionGate resource="posture">
        <button>Save Changes</button>
      </EditPermissionGate>,
    );

    const button = screen.getByRole('button', { name: 'Save Changes' });
    expect(button).toBeInTheDocument();
    expect(button.closest('[aria-disabled="true"]')).not.toBeNull();
  });

  it('hides children entirely when hide=true and user lacks edit permission', () => {
    mockedUsePermissions.mockReturnValue({
      permissions: ['posture:view'],
      roles: ['viewer'],
      isLoading: false,
      hasPermission: (r: string, a: string) => `${r}:${a}` === 'posture:view',
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
      <EditPermissionGate resource="posture" hide fallback={<span>Read only</span>}>
        <button>Save Changes</button>
      </EditPermissionGate>,
    );

    expect(screen.queryByRole('button', { name: 'Save Changes' })).not.toBeInTheDocument();
    expect(screen.getByText('Read only')).toBeInTheDocument();
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
      <EditPermissionGate resource="posture">
        <button>Save Changes</button>
      </EditPermissionGate>,
    );

    expect(container.innerHTML).toBe('');
  });
});
