import type { ReactNode } from 'react';
import { usePermissions } from '../../hooks/usePermissions';

interface PermissionGateProps {
  resource: string;
  action: string;
  children: ReactNode;
  fallback?: ReactNode;
}

/**
 * Conditionally renders children based on the user's permissions.
 * Shows fallback (or nothing) if the user lacks the required permission.
 */
export function PermissionGate({
  resource,
  action,
  children,
  fallback = null,
}: PermissionGateProps) {
  const { hasPermission, isLoading } = usePermissions();

  if (isLoading) return null;
  if (!hasPermission(resource, action)) return <>{fallback}</>;
  return <>{children}</>;
}
