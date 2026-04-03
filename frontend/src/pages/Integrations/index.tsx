import { Navigate } from 'react-router-dom';

/**
 * The standalone Integrations page has been moved into Settings > Integrations.
 * This component redirects to the unified location.
 */
export function IntegrationsPage() {
  return <Navigate to="/settings/integrations" replace />;
}
