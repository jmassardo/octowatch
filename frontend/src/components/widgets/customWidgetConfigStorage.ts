/**
 * LocalStorage-based configuration store for custom query widgets.
 *
 * Each custom widget instance stores its configuration (query ID, visualization
 * type, refresh interval) in localStorage keyed by a unique widget ID.
 * This follows the same pattern as statPillConfigStorage.ts.
 */

import type {
  CustomWidgetConfig,
  CustomWidgetCreate,
  VisualizationType,
} from '../../types/customWidget';

export const CUSTOM_WIDGETS_STORAGE_KEY = 'octowatch-custom-widgets';

/** Generate a unique widget ID for registration in the widget system. */
export function generateCustomWidgetId(): string {
  return `custom-query-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function isVisualizationType(value: unknown): value is VisualizationType {
  return (
    value === 'bar' || value === 'line' || value === 'table' || value === 'stat' || value === 'pie'
  );
}

/** Load all custom widget configurations from localStorage. */
export function loadCustomWidgetConfigs(): CustomWidgetConfig[] {
  if (typeof window === 'undefined') return [];

  try {
    const raw = window.localStorage.getItem(CUSTOM_WIDGETS_STORAGE_KEY);
    if (!raw) return [];

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];

    return parsed.filter(
      (item): item is CustomWidgetConfig =>
        item !== null &&
        typeof item === 'object' &&
        typeof item.id === 'string' &&
        typeof item.title === 'string' &&
        isVisualizationType(item.visualizationType),
    );
  } catch {
    return [];
  }
}

/** Save all custom widget configurations to localStorage. */
export function saveCustomWidgetConfigs(configs: readonly CustomWidgetConfig[]): void {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(CUSTOM_WIDGETS_STORAGE_KEY, JSON.stringify(configs));
}

/** Get a single custom widget configuration by ID. */
export function getCustomWidgetConfig(widgetId: string): CustomWidgetConfig | null {
  const configs = loadCustomWidgetConfigs();
  return configs.find((c) => c.id === widgetId) ?? null;
}

/** Create a new custom widget configuration and persist it. */
export function createCustomWidgetConfig(payload: CustomWidgetCreate): CustomWidgetConfig {
  const configs = loadCustomWidgetConfigs();
  const newConfig: CustomWidgetConfig = {
    id: generateCustomWidgetId(),
    title: payload.title,
    description: payload.description ?? '',
    savedQueryId: payload.savedQueryId ?? null,
    inlineSql: payload.inlineSql ?? '',
    visualizationType: payload.visualizationType,
    refreshIntervalSeconds: payload.refreshIntervalSeconds ?? 0,
    createdAt: new Date().toISOString(),
  };
  configs.push(newConfig);
  saveCustomWidgetConfigs(configs);
  return newConfig;
}

/** Update an existing custom widget configuration. */
export function updateCustomWidgetConfig(
  widgetId: string,
  updates: Partial<Omit<CustomWidgetConfig, 'id' | 'createdAt'>>,
): CustomWidgetConfig | null {
  const configs = loadCustomWidgetConfigs();
  const index = configs.findIndex((c) => c.id === widgetId);
  if (index < 0) return null;

  const updated = { ...configs[index], ...updates } as CustomWidgetConfig;
  configs[index] = updated;
  saveCustomWidgetConfigs(configs);
  return updated;
}

/** Delete a custom widget configuration. */
export function deleteCustomWidgetConfig(widgetId: string): boolean {
  const configs = loadCustomWidgetConfigs();
  const filtered = configs.filter((c) => c.id !== widgetId);
  if (filtered.length === configs.length) return false;
  saveCustomWidgetConfigs(filtered);
  return true;
}
