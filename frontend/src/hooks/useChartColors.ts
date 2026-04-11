import { useSyncExternalStore, useCallback } from 'react';

/**
 * Reads CSS custom property values from the document root.
 *
 * Returns theme-aware color tokens that update when `data-theme`
 * changes, allowing ECharts options to use the current palette
 * without hardcoded color strings.
 */
export function useChartColors() {
  // Subscribe to data-theme attribute changes on <html>
  const subscribe = useCallback((cb: () => void) => {
    const observer = new MutationObserver(cb);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    // Also listen for system color scheme changes (if available)
    let mq: MediaQueryList | null = null;
    if (typeof window.matchMedia === 'function') {
      mq = window.matchMedia('(prefers-color-scheme: light)');
      mq.addEventListener('change', cb);
    }
    return () => {
      observer.disconnect();
      if (mq) mq.removeEventListener('change', cb);
    };
  }, []);

  const getSnapshot = useCallback(() => {
    const s = getComputedStyle(document.documentElement);
    return JSON.stringify({
      chartBg: s.getPropertyValue('--chart-bg').trim() || '#0d1117',
      chartGrid: s.getPropertyValue('--chart-grid').trim() || '#21262d',
      chartText: s.getPropertyValue('--chart-text').trim() || '#8b949e',
      chartTextSecondary: s.getPropertyValue('--chart-text-secondary').trim() || '#6e7681',
      chartTooltipBg: s.getPropertyValue('--chart-tooltip-bg').trim() || '#161b22',
      chartTooltipBorder: s.getPropertyValue('--chart-tooltip-border').trim() || '#30363d',
      chartTooltipFg: s.getPropertyValue('--chart-tooltip-fg').trim() || '#e6edf3',
    });
  }, []);

  const raw = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  return JSON.parse(raw) as {
    chartBg: string;
    chartGrid: string;
    chartText: string;
    chartTextSecondary: string;
    chartTooltipBg: string;
    chartTooltipBorder: string;
    chartTooltipFg: string;
  };
}
