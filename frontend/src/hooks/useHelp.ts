import { useCallback, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { findHelpContent } from '../components/common/helpContent';

export function useHelp() {
  const location = useLocation();
  const [openPath, setOpenPath] = useState<string | null>(null);

  const helpContent = useMemo(() => findHelpContent(location.pathname), [location.pathname]);
  const isHelpOpen = openPath === location.pathname && helpContent !== null;

  const openHelp = useCallback(() => {
    if (helpContent) {
      setOpenPath(location.pathname);
    }
  }, [helpContent, location.pathname]);

  const closeHelp = useCallback(() => {
    setOpenPath(null);
  }, []);

  return {
    helpContent,
    openHelp,
    closeHelp,
    isHelpOpen,
  };
}
