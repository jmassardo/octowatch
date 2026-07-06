import { useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';

/**
 * Manage path-based tab routing with validation, fallback, and query-param preservation.
 *
 * The hook reads the `:tab` param from the current URL (e.g. `/reports/templates`),
 * validates it against the allowed values, and provides a setter that navigates to
 * the new tab while preserving existing query params.
 *
 * If the current URL segment is not a valid tab, the hook returns `defaultTab` and
 * replaces the URL with the canonical path on the next render (via the component).
 *
 * @param basePath - Absolute path prefix without trailing slash (e.g. `/reports`)
 * @param validTabs - Readonly array of allowed tab slugs
 * @param defaultTab - Fallback tab when URL segment is missing or invalid
 */
export function useTabParam<T extends string>(
  basePath: string,
  validTabs: readonly T[],
  defaultTab: T,
): [T, (tab: T, options?: { replace?: boolean }) => void] {
  const { tab } = useParams<{ tab: string }>();
  const navigate = useNavigate();
  const location = useLocation();

  const activeTab: T = (validTabs as readonly string[]).includes(tab ?? '')
    ? (tab as T)
    : defaultTab;

  const setTab = useCallback(
    (newTab: T, opts?: { replace?: boolean }) => {
      navigate(
        { pathname: `${basePath}/${newTab}`, search: location.search },
        { replace: opts?.replace ?? true },
      );
    },
    [basePath, navigate, location.search],
  );

  return [activeTab, setTab];
}
