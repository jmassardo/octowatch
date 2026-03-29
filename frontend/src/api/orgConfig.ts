import { api } from './client';

export interface OrgConfigResponse {
  org_slug: string;
  copilot_cost_per_seat: number;
}

export interface OrgConfigUpdate {
  copilot_cost_per_seat: number | null;
}

export function getOrgConfig(orgSlug: string): Promise<OrgConfigResponse> {
  return api.get<OrgConfigResponse>(`/orgs/${encodeURIComponent(orgSlug)}/config`);
}

export function updateOrgConfig(
  orgSlug: string,
  update: OrgConfigUpdate,
): Promise<OrgConfigResponse> {
  return api.patch<OrgConfigResponse>(
    `/orgs/${encodeURIComponent(orgSlug)}/config`,
    update,
  );
}
