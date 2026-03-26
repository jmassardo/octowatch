import { api } from './client';
import type { RoleDefinition, RoleAssignment, RoleAssignmentCreate, IngestionSource, TopActor } from '../types/admin';

export function listRoles(): Promise<RoleDefinition[]> {
  return api.get<RoleDefinition[]>('/admin/roles');
}

export function listRoleAssignments(): Promise<RoleAssignment[]> {
  return api.get<RoleAssignment[]>('/admin/role-assignments');
}

export function createRoleAssignment(a: RoleAssignmentCreate): Promise<RoleAssignment> {
  return api.post<RoleAssignment>('/admin/role-assignments', a);
}

export function deleteRoleAssignment(id: number): Promise<void> {
  return api.delete<void>(`/admin/role-assignments/${id}`);
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

export function getTopActors(params?: Record<string, string | number | boolean | undefined>): Promise<TopActor[]> {
  return api.get<TopActor[]>('/admin/top-actors', params);
}
