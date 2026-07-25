import { Navigate } from 'react-router';

/**
 * The standalone Integrations page has been moved into Settings > Integrations.
 * This component redirects to the unified location.
 */
export function IntegrationsPage() {
  return <Navigate to="/settings/integrations" replace />;
}
