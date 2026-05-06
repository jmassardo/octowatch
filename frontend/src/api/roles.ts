import { api } from './client';

export interface Role {
  id: number;
  name: string;
  display_name: string;
  description: string | null;
  permissions: string[];
  is_system: boolean;
  is_custom: boolean;
  created_at: string;
  updated_at: string | null;
  assignment_count: number;
}

export interface RoleSummary {
  id: number;
  name: string;
  display_name: string;
  description: string | null;
  permission_count: number;
  is_system: boolean;
  is_custom: boolean;
  created_at: string;
}

export interface CreateRoleRequest {
  name: string;
  display_name: string;
  description?: string;
  permissions: string[];
}

export interface UpdateRoleRequest {
  display_name?: string;
  description?: string;
  permissions?: string[];
}

export function listRbacRoles(): Promise<RoleSummary[]> {
  return api.get<RoleSummary[]>('/admin/roles');
}

export function getRbacRole(id: number): Promise<Role> {
  return api.get<Role>(`/admin/roles/${id}`);
}

export function createRbacRole(data: CreateRoleRequest): Promise<Role> {
  return api.post<Role>('/admin/roles', data);
}

export function updateRbacRole(id: number, data: UpdateRoleRequest): Promise<Role> {
  return api.patch<Role>(`/admin/roles/${id}`, data);
}

export function deleteRbacRole(id: number): Promise<void> {
  return api.delete<void>(`/admin/roles/${id}`);
}
