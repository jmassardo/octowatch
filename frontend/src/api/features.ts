import { api } from './client';

export interface FeatureFlags {
  copilot_insights: boolean;
  velocity: boolean;
  dev_activity: boolean;
  org_health: boolean;
}

export function getFeatures(): Promise<FeatureFlags> {
  return api.get<FeatureFlags>('/features');
}

export function updateFeatures(flags: Partial<FeatureFlags>): Promise<Partial<FeatureFlags>> {
  return api.put<Partial<FeatureFlags>>('/features', flags);
}
