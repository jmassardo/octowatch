import { api } from './client';

export interface CopilotOverview {
  acceptance_rate_days: string[];
  acceptance_rate_values: number[];
  acceptance_threshold: number;
  languages: Array<{ lang: string; pct: number; color: string }>;
  total_active_users: number;
  total_engaged_users: number;
  error?: string;
  message?: string;
}

export interface AdoptionTier {
  id: string;
  label: string;
  count: number;
  color: string;
  desc: string;
}

export interface PowerUser {
  user: string;
  days_active: number;
  features_used: number;
}

export interface MinimalUser {
  user: string;
  days_active: number;
  last_feature: string;
}

export interface CopilotAdoption {
  tiers: AdoptionTier[];
  total_adoption: number;
  power_users: PowerUser[];
  feature_adoption: Array<{ feature: string; pct: number; color: string }>;
  minimal_users: MinimalUser[];
  error?: string;
  message?: string;
}

export interface CopilotModels {
  models: Array<{ model: string; pct: number; color: string }>;
  features: Array<{ feature: string; count: number; color: string }>;
  editors: Array<{ name: string; count: number; pct: number }>;
  error?: string;
  message?: string;
}

export interface CopilotAnomaly {
  id: number;
  severity: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  timestamp: string;
  team: string;
}

export interface CopilotAnomalies {
  anomalies: CopilotAnomaly[];
  error?: string;
  message?: string;
}

export function getCopilotOverview(): Promise<CopilotOverview> {
  return api.get<CopilotOverview>('/copilot/overview');
}

export function getCopilotAdoption(): Promise<CopilotAdoption> {
  return api.get<CopilotAdoption>('/copilot/adoption');
}

export function getCopilotModels(): Promise<CopilotModels> {
  return api.get<CopilotModels>('/copilot/models');
}

export function getCopilotAnomalies(): Promise<CopilotAnomalies> {
  return api.get<CopilotAnomalies>('/copilot/anomalies');
}
