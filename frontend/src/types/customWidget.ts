/**
 * Types for the custom query widget system.
 *
 * Custom widgets allow users to create dashboard widgets backed by
 * saved queries with configurable visualization types and refresh intervals.
 */

/** Supported visualization types for custom query widgets. */
export type VisualizationType = 'bar' | 'line' | 'table' | 'stat' | 'pie';

/** Configuration for a single custom query widget instance. */
export interface CustomWidgetConfig {
  /** Unique identifier for this widget instance. */
  readonly id: string;
  /** Display title shown in the widget header. */
  readonly title: string;
  /** Optional description for the widget. */
  readonly description: string;
  /** ID of the saved query to execute, or null for inline SQL. */
  readonly savedQueryId: number | null;
  /** Inline SQL text when no saved query is selected. */
  readonly inlineSql: string;
  /** Selected visualization type. */
  readonly visualizationType: VisualizationType;
  /** Auto-refresh interval in seconds (0 = refresh on page load only). */
  readonly refreshIntervalSeconds: number;
  /** Timestamp of when this widget was created. */
  readonly createdAt: string;
}

/** Payload for creating a new custom widget. */
export interface CustomWidgetCreate {
  readonly title: string;
  readonly description?: string;
  readonly savedQueryId?: number | null;
  readonly inlineSql?: string;
  readonly visualizationType: VisualizationType;
  readonly refreshIntervalSeconds?: number;
}

/** All visualization type options with labels. */
export const VISUALIZATION_TYPE_OPTIONS: readonly {
  readonly value: VisualizationType;
  readonly label: string;
  readonly description: string;
}[] = [
  { value: 'bar', label: 'Bar Chart', description: 'Compare values across categories' },
  { value: 'line', label: 'Line Chart', description: 'Show trends over time' },
  { value: 'table', label: 'Table', description: 'Display raw query results in rows' },
  { value: 'stat', label: 'Stat Card', description: 'Show a single headline number' },
  { value: 'pie', label: 'Pie Chart', description: 'Show proportion of parts to whole' },
];
