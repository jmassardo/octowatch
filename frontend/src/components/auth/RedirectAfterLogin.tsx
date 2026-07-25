import { Navigate } from 'react-router';
import { consumeReturnUrl } from '../../hooks/useSessionTimeout';

/**
 * Handles the root `/` route redirect after authentication.
 * If there is a saved return URL (from a session expiry), redirects there.
 * Otherwise, redirects to /dashboard as the default landing page.
 */
export function RedirectAfterLogin() {
  const savedUrl = consumeReturnUrl();
  const target = savedUrl ?? '/dashboard';
  return <Navigate to={target} replace />;
}
