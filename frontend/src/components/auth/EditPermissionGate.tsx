import type { ReactNode } from 'react';
import { usePermissions } from '../../hooks/usePermissions';

interface EditPermissionGateProps {
  /** The resource to check edit permission for */
  resource: string;
  /** Content to render - will be wrapped with disabled styling if no edit permission */
  children: ReactNode;
  /** Optional fallback when user cannot edit (defaults to rendering children as disabled) */
  fallback?: ReactNode;
  /** If true, completely hides children instead of disabling (default: false) */
  hide?: boolean;
}

/**
 * Wraps edit controls and applies disabled state when user lacks edit permission.
 * Use this around buttons, forms, or action panels that require write access.
 *
 * - If user has `resource:edit` → renders children normally
 * - If user lacks edit but `hide=false` → renders children in a disabled wrapper
 * - If user lacks edit and `hide=true` → renders fallback or nothing
 */
export function EditPermissionGate({
  resource,
  children,
  fallback = null,
  hide = false,
}: EditPermissionGateProps) {
  const { canEdit, isLoading } = usePermissions();

  if (isLoading) return null;

  if (canEdit(resource)) {
    return <>{children}</>;
  }

  if (hide) {
    return <>{fallback}</>;
  }

  return (
    <div
      aria-disabled="true"
      title="You do not have edit permission for this resource"
      style={{ opacity: 0.5, pointerEvents: 'none', cursor: 'not-allowed' }}
    >
      {children}
    </div>
  );
}
