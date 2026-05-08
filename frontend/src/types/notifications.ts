// ── In-App Notification Types ───────────────────────────────────────────────

export type NotificationSeverity = 'info' | 'warning' | 'critical';
export type NotificationSource = 'detection' | 'sync' | 'system';

export interface NotificationItem {
  readonly id: number;
  readonly user_id: string;
  readonly title: string;
  readonly message: string;
  readonly severity: NotificationSeverity;
  readonly read: boolean;
  readonly source: NotificationSource;
  readonly link: string | null;
  readonly created_at: string;
}

export interface NotificationListResponse {
  readonly items: readonly NotificationItem[];
  readonly total: number;
  readonly page: number;
  readonly page_size: number;
  readonly has_next: boolean;
  readonly unread_count: number;
}

export interface MarkReadResponse {
  readonly updated: number;
}

// ── Notification Preferences Types ──────────────────────────────────────────

export interface NotificationPreferences {
  readonly in_app_enabled: boolean;
  readonly email_enabled: boolean;
  readonly slack_enabled: boolean;
  readonly severity_filter: NotificationSeverity;
  readonly detection_alerts: boolean;
  readonly sync_alerts: boolean;
  readonly system_alerts: boolean;
  readonly updated_at: string;
}

export interface NotificationPreferencesUpdate {
  in_app_enabled?: boolean;
  email_enabled?: boolean;
  slack_enabled?: boolean;
  severity_filter?: NotificationSeverity;
  detection_alerts?: boolean;
  sync_alerts?: boolean;
  system_alerts?: boolean;
}

export interface NotificationListParams {
  page?: number;
  page_size?: number;
  severity?: NotificationSeverity;
  read?: boolean;
  source?: NotificationSource;
}
