import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { usePermissions } from './usePermissions';

const mockPermissions = {
  user_id: 'user-1',
  roles: ['analyst', 'viewer'],
  permissions: ['events:view', 'detections:view', 'reports:view'],
  scopes: { orgs: null, repos: null },
};

vi.mock('../api/permissions', () => ({
  getMyPermissions: vi.fn().mockResolvedValue({
    user_id: 'user-1',
    roles: ['analyst', 'viewer'],
    permissions: ['events:view', 'detections:view', 'reports:view'],
    scopes: { orgs: null, repos: null },
  }),
}));

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe('usePermissions', () => {
  it('returns permissions and roles after loading', async () => {
    const { result } = renderHook(() => usePermissions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.permissions).toEqual(mockPermissions.permissions);
    expect(result.current.roles).toEqual(mockPermissions.roles);
  });

  it('hasPermission returns true for exact match', async () => {
    const { result } = renderHook(() => usePermissions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.hasPermission('events', 'view')).toBe(true);
    expect(result.current.hasPermission('events', 'delete')).toBe(false);
    expect(result.current.hasPermission('admin_users', 'view')).toBe(false);
  });

  it('hasAnyPermission returns true if any permission matches', async () => {
    const { result } = renderHook(() => usePermissions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(
      result.current.hasAnyPermission([
        ['events', 'view'],
        ['admin_users', 'view'],
      ]),
    ).toBe(true);
    expect(
      result.current.hasAnyPermission([
        ['admin_users', 'view'],
        ['admin_settings', 'view'],
      ]),
    ).toBe(false);
  });

  it('hasRole returns true for matching role', async () => {
    const { result } = renderHook(() => usePermissions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.hasRole('analyst')).toBe(true);
    expect(result.current.hasRole('super_admin')).toBe(false);
  });
});

describe('usePermissions wildcard matching', () => {
  it('handles *:* wildcard (super_admin)', async () => {
    const { getMyPermissions } = await import('../api/permissions');
    vi.mocked(getMyPermissions).mockResolvedValueOnce({
      user_id: 'admin-1',
      roles: ['super_admin'],
      permissions: ['*:*'],
      scopes: { orgs: null, repos: null },
    });

    const { result } = renderHook(() => usePermissions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.hasPermission('anything', 'goes')).toBe(true);
    expect(result.current.hasPermission('admin_users', 'delete')).toBe(true);
  });

  it('handles resource:* wildcard', async () => {
    const { getMyPermissions } = await import('../api/permissions');
    vi.mocked(getMyPermissions).mockResolvedValueOnce({
      user_id: 'user-2',
      roles: ['rule_author'],
      permissions: ['rules:*', 'events:view'],
      scopes: { orgs: null, repos: null },
    });

    const { result } = renderHook(() => usePermissions(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.hasPermission('rules', 'view')).toBe(true);
    expect(result.current.hasPermission('rules', 'create')).toBe(true);
    expect(result.current.hasPermission('rules', 'delete')).toBe(true);
    expect(result.current.hasPermission('events', 'view')).toBe(true);
    expect(result.current.hasPermission('events', 'delete')).toBe(false);
  });
});
