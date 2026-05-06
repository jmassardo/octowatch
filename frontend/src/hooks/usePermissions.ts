import { useQuery } from '@tanstack/react-query';
import { getMyPermissions } from '../api/permissions';

interface UsePermissionsReturn {
  permissions: string[];
  roles: string[];
  isLoading: boolean;
  hasPermission: (resource: string, action: string) => boolean;
  hasAnyPermission: (checks: Array<[string, string]>) => boolean;
  hasRole: (role: string) => boolean;
}

/**
 * Hook providing permission checks against the current user's RBAC permissions.
 *
 * Fetches permissions from `/auth/me/permissions` and caches them for 5 minutes.
 * Supports wildcard matching: `*:*` grants all, `resource:*` grants all actions on a resource.
 */
export function usePermissions(): UsePermissionsReturn {
  const { data, isLoading } = useQuery({
    queryKey: ['permissions'],
    queryFn: getMyPermissions,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000,
  });

  const permissions = data?.permissions ?? [];
  const roles = data?.roles ?? [];

  const hasPermission = (resource: string, action: string): boolean => {
    if (permissions.includes('*:*')) return true;
    if (permissions.includes(`${resource}:*`)) return true;
    if (permissions.includes(`${resource}:${action}`)) return true;
    return false;
  };

  const hasAnyPermission = (checks: Array<[string, string]>): boolean => {
    return checks.some(([r, a]) => hasPermission(r, a));
  };

  const hasRole = (role: string): boolean => roles.includes(role);

  return { permissions, roles, isLoading, hasPermission, hasAnyPermission, hasRole };
}
