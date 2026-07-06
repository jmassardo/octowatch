import { api } from './client';

export interface Team {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  member_count: number;
  role_count: number;
  created_at: string;
}

export interface TeamDetail {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  members: TeamMember[];
  roles: TeamRole[];
  created_at: string;
}

export interface TeamMember {
  user_login: string;
  added_at: string;
}

export interface TeamRole {
  role_id: number;
  role_name: string;
  org_slug: string | null;
  repo_slugs: string[] | null;
}

export interface CreateTeamRequest {
  name: string;
  description?: string;
}

export function listTeams(): Promise<Team[]> {
  return api.get<Team[]>('/admin/teams');
}

export function getTeam(id: number): Promise<TeamDetail> {
  return api.get<TeamDetail>(`/admin/teams/${id}`);
}

export function createTeam(data: CreateTeamRequest): Promise<Team> {
  return api.post<Team>('/admin/teams', data);
}

export function updateTeam(id: number, data: Partial<CreateTeamRequest>): Promise<Team> {
  return api.patch<Team>(`/admin/teams/${id}`, data);
}

export function deleteTeam(id: number): Promise<void> {
  return api.delete<void>(`/admin/teams/${id}`);
}

export function addTeamMember(teamId: number, userLogin: string): Promise<void> {
  return api.post<void>(`/admin/teams/${teamId}/members`, { user_login: userLogin });
}

export function removeTeamMember(teamId: number, userLogin: string): Promise<void> {
  return api.delete<void>(`/admin/teams/${teamId}/members/${userLogin}`);
}

export function assignTeamRole(teamId: number, roleId: number, orgSlug?: string): Promise<void> {
  return api.post<void>(`/admin/teams/${teamId}/roles`, { role_id: roleId, org_slug: orgSlug });
}

export function removeTeamRole(teamId: number, roleId: number): Promise<void> {
  return api.delete<void>(`/admin/teams/${teamId}/roles/${roleId}`);
}

export type TeamsNotificationSource =
  'detections' | 'sync_errors' | 'system_health' | 'threat_intel';

export type TeamsChannelKey =
  'default' | 'detections' | 'sync_errors' | 'system_health' | 'threat_intel';

export interface TeamsConfigResponse {
  channel_webhook_configured: Record<TeamsChannelKey, boolean>;
  channel_webhooks_masked: Record<TeamsChannelKey, string | null>;
  source_mappings: Record<TeamsNotificationSource, TeamsChannelKey>;
  notification_settings: Record<TeamsNotificationSource, boolean>;
}

export interface TeamsConfigUpdate {
  channel_webhooks: Record<TeamsChannelKey, string>;
  source_mappings: Record<TeamsNotificationSource, TeamsChannelKey>;
  notification_settings: Record<TeamsNotificationSource, boolean>;
  clear_channels: TeamsChannelKey[];
}

export interface TeamsTestResponse {
  ok: boolean;
  channel: TeamsChannelKey;
  message: string;
}

export function getTeamsConfig(): Promise<TeamsConfigResponse> {
  return api.get<TeamsConfigResponse>('/integrations/teams/config');
}

export function updateTeamsConfig(payload: TeamsConfigUpdate): Promise<TeamsConfigResponse> {
  return api.put<TeamsConfigResponse>('/integrations/teams/config', payload);
}

export function testTeamsConnection(channel?: TeamsChannelKey): Promise<TeamsTestResponse> {
  return api.post<TeamsTestResponse>('/integrations/teams/test', channel ? { channel } : undefined);
}
