import type { EventResponse, EventListParams } from '../../types/events';

/** Mapping from recognised search-bar keys to {@link EventListParams} fields. */
export const SEARCH_KEY_MAP: Record<string, keyof EventListParams> = {
  org: 'org',
  action: 'action',
  actor: 'actor',
  repo: 'repo',
  since: 'since',
  until: 'until',
  after: 'since',
  before: 'until',
  namespace: 'namespace',
  ip: 'source_ip',
  source_ip: 'source_ip',
  country: 'geo_country_code',
  geo_country_code: 'geo_country_code',
  bot: 'actor_is_bot',
};

/**
 * Extract `key:value` filter tokens from free-text search input.
 * Recognised keys are mapped to {@link EventListParams} fields.
 */
export function parseSearchFilters(input: string): Partial<EventListParams> {
  if (!input) return {};
  const filters: Record<string, string | boolean> = {};
  const pattern =
    /\b(org|action|actor|repo|since|until|after|before|namespace|ip|source_ip|country|geo_country_code|bot):(\S+)/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(input)) !== null) {
    const paramKey = SEARCH_KEY_MAP[match[1]];
    if (paramKey) {
      if (paramKey === 'actor_is_bot') {
        filters[paramKey] = match[2].toLowerCase() === 'true';
      } else {
        filters[paramKey] = match[2];
      }
    }
  }
  return filters as Partial<EventListParams>;
}

/** Sanitize a cell value to prevent spreadsheet formula injection. */
function sanitizeCell(value: string): string {
  const s = String(value);
  if (/^[=+\-@\t\r]/.test(s)) {
    return "'" + s;
  }
  return s;
}

/** Build a CSV string from event data and trigger a browser download. */
export function downloadCsv(events: readonly EventResponse[]): void {
  const headers = ['Timestamp', 'Action', 'Actor', 'Repository', 'Organization', 'IP', 'Country'];
  const rows = events.map((e) => [
    e.created_at,
    e.action,
    e.actor ?? '',
    e.repo ?? '',
    e.org ?? '',
    e.source_ip ?? '',
    e.geo_country_code ?? '',
  ]);
  const csv = [headers, ...rows]
    .map((row) =>
      row.map((cell) => `"${sanitizeCell(String(cell)).replace(/"/g, '""')}"`).join(','),
    )
    .join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `octowatch-events-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
