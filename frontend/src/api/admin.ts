import { api } from './client';
import type { RoleDefinition, RoleAssignment, RoleAssignmentCreate, IngestionSource } from '../types/admin';

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
