import { Navigate, useLocation } from 'react-router-dom';

/**
 * Redirect from a legacy `?tab=X` URL to a path-based `/base/X` URL.
 *
 * Validates the tab value against allowed tabs. Preserves all other query params
 * and removes the `tab` param from the resulting URL.
 *
 * Usage in route config:
 * ```
 * { path: '/reports', element: <LegacyTabRedirect basePath="/reports" validTabs={[...]} defaultTab="templates" /> }
 * ```
 */
export function LegacyTabRedirect({
  basePath,
  validTabs,
  defaultTab,
}: {
  basePath: string;
  validTabs: readonly string[];
  defaultTab: string;
}) {
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  const tabFromQuery = searchParams.get('tab');

  const resolvedTab = tabFromQuery && validTabs.includes(tabFromQuery) ? tabFromQuery : defaultTab;

  // Remove the tab param, keep everything else
  searchParams.delete('tab');
  const remainingSearch = searchParams.toString();
  const to = `${basePath}/${resolvedTab}${remainingSearch ? `?${remainingSearch}` : ''}`;

  return <Navigate to={to} replace />;
}
