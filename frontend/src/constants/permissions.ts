/**
 * Permission resource constants matching the backend VALID_RESOURCES.
 * Use these instead of raw strings for type safety and refactoring support.
 */
export const RESOURCES = {
  DASHBOARD: 'dashboard',
  DETECTIONS: 'detections',
  EVENTS: 'events',
  QUERIES: 'queries',
  POSTURE: 'posture',
  ADVANCED_SECURITY: 'advanced_security',
  VELOCITY: 'velocity',
  DEV_ACTIVITY: 'dev_activity',
  CROSS_ORG: 'cross_org',
  COPILOT: 'copilot',
  ORG_HEALTH: 'org_health',
  WORKFLOW_SECURITY: 'workflow_security',
  WORKFLOW_HEALTH: 'workflow_health',
  REPORTS: 'reports',
  RULES: 'rules',
  ADMIN_SETTINGS: 'admin_settings',
  ADMIN_USERS: 'admin_users',
  ADMIN_ROLES: 'admin_roles',
  ADMIN_TEAMS: 'admin_teams',
  AUDIT_LOG: 'audit_log',
  PLAYBOOKS: 'playbooks',
  SUPPLY_CHAIN: 'supply_chain',
  PACKAGES: 'packages',
  USER_BEHAVIOR: 'user_behavior',
  NOTIFICATIONS: 'notifications',
  COMPLIANCE: 'compliance',
  TELEMETRY: 'telemetry',
  PLATFORM_USAGE: 'platform_usage',
  SYNC_STATUS: 'sync_status',
  THREAT_INTEL: 'threat_intel',
  PROFILE: 'profile',
} as const;

export type Resource = (typeof RESOURCES)[keyof typeof RESOURCES];

/**
 * Permission action constants matching the backend VALID_ACTIONS.
 */
export const ACTIONS = {
  VIEW: 'view',
  CREATE: 'create',
  EDIT: 'edit',
  DELETE: 'delete',
  EXPORT: 'export',
  SHARE: 'share',
  ASSIGN: 'assign',
  DISMISS: 'dismiss',
  EXECUTE: 'execute',
  ADMIN: 'admin',
} as const;

export type Action = (typeof ACTIONS)[keyof typeof ACTIONS];
