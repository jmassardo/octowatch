import { api } from './client';

// ─── Types ──────────────────────────────────────────────────────────────────

export interface WidgetLayoutItem {
  readonly widget_id: string;
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
}

export interface DashboardConfig {
  readonly id: string;
  readonly user_id: string;
  readonly layout: readonly WidgetLayoutItem[];
  readonly persona: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface DashboardConfigUpdate {
  readonly layout: readonly WidgetLayoutItem[];
  readonly persona: string;
}

export interface CatalogWidget {
  readonly id: string;
  readonly title: string;
  readonly description: string;
  readonly category: string;
  readonly default_w: number;
  readonly default_h: number;
}

export interface WidgetCatalogResponse {
  readonly widgets: readonly CatalogWidget[];
}

export interface PersonaLayoutItem {
  readonly widget_id: string;
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
}

export interface Persona {
  readonly id: string;
  readonly label: string;
  readonly description: string;
  readonly default_layout: readonly PersonaLayoutItem[];
}

export interface PersonaListResponse {
  readonly personas: readonly Persona[];
}

// ─── API functions ──────────────────────────────────────────────────────────

/** Fetch the current user's dashboard configuration. */
export function getDashboardConfig(): Promise<DashboardConfig> {
  return api.get<DashboardConfig>('/dashboard/config');
}

/** Save/update the current user's dashboard configuration. */
export function updateDashboardConfig(body: DashboardConfigUpdate): Promise<DashboardConfig> {
  return api.put<DashboardConfig>('/dashboard/config', body);
}

/** Fetch the full widget catalog. */
export function getWidgetCatalog(): Promise<WidgetCatalogResponse> {
  return api.get<WidgetCatalogResponse>('/dashboard/widgets');
}

/** Fetch available personas with their default layouts. */
export function getPersonas(): Promise<PersonaListResponse> {
  return api.get<PersonaListResponse>('/dashboard/personas');
}
