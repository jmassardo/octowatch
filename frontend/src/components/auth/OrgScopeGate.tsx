import type { ReactNode } from 'react';
import { usePermissions } from '../../hooks/usePermissions';

interface OrgScopeGateProps {
  /** The org slug to check scope for */
  org: string;
  /** Content to render when org is in scope */
  children: ReactNode;
  /** Optional fallback when org is not in scope */
  fallback?: ReactNode;
}

/**
 * Conditionally renders children based on whether an org is within the user's RBAC scope.
 * Global-scoped users see everything. Org-scoped users only see their assigned orgs.
 */
export function OrgScopeGate({ org, children, fallback = null }: OrgScopeGateProps) {
  const { isOrgInScope, isLoading } = usePermissions();

  if (isLoading) return null;
  if (!isOrgInScope(org)) return <>{fallback}</>;
  return <>{children}</>;
}
