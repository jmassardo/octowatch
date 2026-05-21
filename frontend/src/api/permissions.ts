import { api } from './client';

export interface PermissionsResponse {
  user_id: string;
  roles: string[];
  permissions: string[];
  scopes: {
    orgs: string[] | null;
    repos: string[] | null;
    scope_type: string;
  };
}

export function getMyPermissions(): Promise<PermissionsResponse> {
  return api.get<PermissionsResponse>('/auth/me/permissions');
}
