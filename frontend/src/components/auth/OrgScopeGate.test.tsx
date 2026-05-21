import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { OrgScopeGate } from './OrgScopeGate';
import * as usePermissionsModule from '../../hooks/usePermissions';

vi.mock('../../hooks/usePermissions');
const mockedUsePermissions = vi.mocked(usePermissionsModule.usePermissions);

function renderWithProviders(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('OrgScopeGate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders children when user has global scope', () => {
    mockedUsePermissions.mockReturnValue({
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
    });

    renderWithProviders(
      <OrgScopeGate org="my-org">
        <span>Org content</span>
      </OrgScopeGate>,
    );

    expect(screen.getByText('Org content')).toBeInTheDocument();
  });

  it('renders children when org is in user scope', () => {
    mockedUsePermissions.mockReturnValue({
      permissions: ['posture:view'],
      roles: ['security_analyst'],
      isLoading: false,
      hasPermission: () => true,
      hasAnyPermission: () => true,
      hasRole: () => true,
      scopedOrgs: ['my-org', 'other-org'],
      scopedRepos: [],
      scopeType: 'org',
      isOrgInScope: (org: string) => ['my-org', 'other-org'].includes(org),
      isRepoInScope: () => true,
      canEdit: () => false,
    });

    renderWithProviders(
      <OrgScopeGate org="my-org">
        <span>Org content</span>
      </OrgScopeGate>,
    );

    expect(screen.getByText('Org content')).toBeInTheDocument();
  });

  it('renders fallback when org is not in user scope', () => {
    mockedUsePermissions.mockReturnValue({
      permissions: ['posture:view'],
      roles: ['security_analyst'],
      isLoading: false,
      hasPermission: () => true,
      hasAnyPermission: () => true,
      hasRole: () => true,
      scopedOrgs: ['my-org'],
      scopedRepos: [],
      scopeType: 'org',
      isOrgInScope: (org: string) => org === 'my-org',
      isRepoInScope: () => false,
      canEdit: () => false,
    });

    renderWithProviders(
      <OrgScopeGate org="restricted-org" fallback={<span>No access</span>}>
        <span>Org content</span>
      </OrgScopeGate>,
    );

    expect(screen.queryByText('Org content')).not.toBeInTheDocument();
    expect(screen.getByText('No access')).toBeInTheDocument();
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
      <OrgScopeGate org="my-org">
        <span>Content</span>
      </OrgScopeGate>,
    );

    expect(container.innerHTML).toBe('');
  });
});
