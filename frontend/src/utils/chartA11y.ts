/**
 * Accessibility helpers for chart components.
 *
 * Provides utilities to generate descriptive text and screen-reader-only
 * data table alternatives for ECharts visualizations.
 */

/** Describe a bar chart dataset for an aria-label. */
export function describeBarChart(
  title: string | undefined,
  xAxisData: string[],
  series: { name: string; data: number[] }[],
): string {
  const label = title ? `${title}. ` : '';
  const parts = series.map((s) => {
    const total = s.data.reduce((a, b) => a + b, 0);
    return `${s.name}: total ${total} across ${xAxisData.length} categories`;
  });
  return `${label}Bar chart. ${parts.join('. ')}.`;
}

/** Describe a line/area chart dataset for an aria-label. */
export function describeLineAreaChart(
  title: string | undefined,
  xAxisData: string[],
  series: { name: string; data: number[] }[],
): string {
  const label = title ? `${title}. ` : '';
  const parts = series.map((s) => {
    const min = Math.min(...s.data);
    const max = Math.max(...s.data);
    return `${s.name}: values from ${min} to ${max} over ${xAxisData.length} points`;
  });
  return `${label}Line chart. ${parts.join('. ')}.`;
}

/** Describe a geo map for an aria-label. */
export function describeGeoMap(
  locations: readonly { city: string; country: string }[],
): string {
  if (locations.length === 0) return 'Geo map with no locations.';
  const names = locations
    .map((l) => [l.city, l.country].filter(Boolean).join(', '))
    .join('; ');
  return `Geo map showing ${locations.length} location${locations.length === 1 ? '' : 's'}: ${names}.`;
}

/**
 * Build row data for a screen-reader-only data table alternative to a chart.
 * Returns headers and rows that can be rendered in a hidden `<table>`.
 */
export function chartToTableData(
  xAxisLabel: string,
  xAxisData: string[],
  series: { name: string; data: number[] }[],
): { headers: string[]; rows: (string | number)[][] } {
  const headers = [xAxisLabel, ...series.map((s) => s.name)];
  const rows = xAxisData.map((x, i) => [x, ...series.map((s) => s.data[i] ?? 0)] as (string | number)[]);
  return { headers, rows };
}
