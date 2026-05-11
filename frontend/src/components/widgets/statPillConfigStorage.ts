import {
  DEFAULT_ENABLED_PILLS,
  DEFAULT_PILL_ORDER,
  STAT_PILL_REGISTRY,
  type ThresholdConfig,
} from './statPillRegistry';

export const STAT_PILL_STORAGE_KEY = 'octowatch-stat-pills-config';

export interface StatPillConfig {
  enabledPills: string[];
  order: string[];
  thresholds: Record<string, ThresholdConfig>;
}

function getDefaultThresholds(): Record<string, ThresholdConfig> {
  return Object.fromEntries(
    Object.values(STAT_PILL_REGISTRY).map((metric) => [metric.id, { ...metric.defaultThresholds }]),
  );
}

export function getDefaultStatPillConfig(): StatPillConfig {
  return {
    enabledPills: [...DEFAULT_ENABLED_PILLS],
    order: [...DEFAULT_PILL_ORDER],
    thresholds: getDefaultThresholds(),
  };
}

function sanitizeIds(ids: unknown): string[] {
  if (!Array.isArray(ids)) return [];
  return ids.filter((id): id is string => typeof id === 'string' && id in STAT_PILL_REGISTRY);
}

function sanitizeThresholds(value: unknown): Record<string, ThresholdConfig> {
  const defaults = getDefaultThresholds();
  if (!value || typeof value !== 'object') return defaults;

  const merged: Record<string, ThresholdConfig> = { ...defaults };
  for (const [metricId, thresholds] of Object.entries(value as Record<string, unknown>)) {
    if (!(metricId in STAT_PILL_REGISTRY) || !thresholds || typeof thresholds !== 'object')
      continue;
    const warning = Number((thresholds as { warning?: unknown }).warning);
    const critical = Number((thresholds as { critical?: unknown }).critical);
    if (!Number.isFinite(warning) || !Number.isFinite(critical)) continue;
    merged[metricId] = { warning, critical };
  }
  return merged;
}

export function loadStatPillConfig(): StatPillConfig {
  if (typeof window === 'undefined') {
    return getDefaultStatPillConfig();
  }

  const defaults = getDefaultStatPillConfig();

  try {
    const stored = window.localStorage.getItem(STAT_PILL_STORAGE_KEY);
    if (!stored) return defaults;

    const parsed = JSON.parse(stored) as Partial<StatPillConfig>;
    const enabledPills = sanitizeIds(parsed.enabledPills);
    const storedOrder = sanitizeIds(parsed.order);
    const seen = new Set<string>();
    const order = [...storedOrder, ...DEFAULT_PILL_ORDER].filter((id) => {
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });

    return {
      enabledPills: enabledPills.length > 0 ? enabledPills : defaults.enabledPills,
      order,
      thresholds: sanitizeThresholds(parsed.thresholds),
    };
  } catch {
    return defaults;
  }
}

export function saveStatPillConfig(config: StatPillConfig): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(STAT_PILL_STORAGE_KEY, JSON.stringify(config));
}
