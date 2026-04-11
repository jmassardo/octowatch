import { api } from './client';
import type {
  RoleDefinition,
  RoleAssignment,
  RoleAssignmentCreate,
  IngestionSource,
  ActiveSession,
  OrgTeam,
} from '../types/admin';

/* ── Role management ───────────────────────────────────────────────── */

export function listRoles(): Promise<RoleDefinition[]> {
  return api.get<RoleDefinition[]>('/admin/roles');
}

export function listRoleAssignments(): Promise<RoleAssignment[]> {
  return api.get<RoleAssignment[]>('/admin/assignments');
}

export function createRoleAssignment(a: RoleAssignmentCreate): Promise<RoleAssignment> {
  return api.post<RoleAssignment>('/admin/assignments', a);
}

export function deleteRoleAssignment(id: number): Promise<void> {
  return api.delete<void>(`/admin/assignments/${id}`);
}

export function listIngestionSources(): Promise<IngestionSource[]> {
  return api.get<IngestionSource[]>('/admin/ingestion-sources');
}

export function createIngestionSource(s: Partial<IngestionSource>): Promise<IngestionSource> {
  return api.post<IngestionSource>('/admin/ingestion-sources', s);
}

export function deleteIngestionSource(id: number): Promise<void> {
  return api.delete<void>(`/admin/ingestion-sources/${id}`);
}

export function getActiveSessions(): Promise<ActiveSession[]> {
  return api.get<ActiveSession[]>('/admin/sessions');
}

export function listSyncedTeams(): Promise<OrgTeam[]> {
  return api.get<OrgTeam[]>('/admin/teams');
}

/* ── Retention policies ────────────────────────────────────────────── */

export interface RetentionPolicyItem {
  table_name: string;
  time_column: string;
  retention_days: number;
  default_days: number;
  row_count: number;
  size_bytes: number;
}

export interface RetentionPoliciesResponse {
  policies: RetentionPolicyItem[];
}

export function getRetentionPolicies(): Promise<RetentionPoliciesResponse> {
  return api.get<RetentionPoliciesResponse>('/admin/retention');
}

export function updateRetentionPolicies(
  policies: Record<string, number>,
): Promise<RetentionPoliciesResponse> {
  return api.put<RetentionPoliciesResponse>('/admin/retention', { policies });
}

/* ── Archive management ────────────────────────────────────────────── */

export interface ArchiveFileInfo {
  key: string;
  size_bytes: number;
  last_modified: string;
}

export function listArchives(table?: string): Promise<ArchiveFileInfo[]> {
  const params = table ? `?table=${encodeURIComponent(table)}` : '';
  return api.get<ArchiveFileInfo[]>(`/admin/archive/list${params}`);
}

export function restoreArchive(archivePath: string): Promise<{ archive_path: string; restored_rows: number }> {
  return api.post<{ archive_path: string; restored_rows: number }>('/admin/archive/restore', {
    archive_path: archivePath,
  });
}

/* ── GDPR erasure ──────────────────────────────────────────────────── */

export interface GdprEraseResponse {
  github_login: string;
  pseudonym: string;
  affected_tables: Record<string, number>;
}

export function gdprErase(githubLogin: string): Promise<GdprEraseResponse> {
  return api.post<GdprEraseResponse>('/admin/gdpr/erase', {
    github_login: githubLogin,
  });
}
