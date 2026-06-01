import { useQuery } from '@tanstack/react-query';
import { getMyPermissions } from '../api/permissions';

interface UsePermissionsReturn {
  permissions: string[];
  roles: string[];
  isLoading: boolean;
  hasPermission: (resource: string, action: string) => boolean;
  hasAnyPermission: (checks: Array<[string, string]>) => boolean;
  hasRole: (role: string) => boolean;
  scopedOrgs: string[];
  scopedRepos: string[];
  scopeType: string;
  isOrgInScope: (org: string) => boolean;
  isRepoInScope: (repo: string) => boolean;
  canEdit: (resource: string) => boolean;
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
  const scopedOrgs = data?.scopes?.orgs ?? [];
  const scopedRepos = data?.scopes?.repos ?? [];
  const scopeType = data?.scopes?.scope_type ?? 'global';

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

  const isOrgInScope = (org: string): boolean => {
    if (scopeType === 'global') return true;
    return scopedOrgs.includes(org);
  };

  const isRepoInScope = (repo: string): boolean => {
    if (scopeType === 'global') return true;
    if (scopeType === 'org') {
      const orgPart = repo.split('/')[0];
      return orgPart ? scopedOrgs.includes(orgPart) : false;
    }
    return scopedRepos.includes(repo);
  };

  const canEdit = (resource: string): boolean => {
    return hasPermission(resource, 'edit');
  };

  return {
    permissions,
    roles,
    isLoading,
    hasPermission,
    hasAnyPermission,
    hasRole,
    scopedOrgs,
    scopedRepos,
    scopeType,
    isOrgInScope,
    isRepoInScope,
    canEdit,
  };
}
