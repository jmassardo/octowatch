import { api } from './client';

/* ── Response types ─────────────────────────────────────────────────────── */

export interface PackageSummary {
  total_packages: number;
  public_packages: number;
  private_packages: number;
  by_type: Record<string, number>;
  newly_public: number;
  stale_images: number;
  open_alerts: number;
}

export interface PackageAlert {
  id: number;
  package_id: number;
  package_name: string;
  package_org: string;
  alert_type: string;
  severity: string;
  message: string;
  detected_at: string;
  resolved_at: string | null;
  status: string;
}

export interface PackageAlertList {
  alerts: PackageAlert[];
  total: number;
}

export interface PackageInventoryItem {
  id: number;
  org: string;
  repo: string | null;
  name: string;
  package_type: string;
  visibility: string;
  owner: string | null;
  versions_count: number;
  latest_version: string | null;
  last_published_at: string | null;
  is_stale: boolean;
  published_outside_actions: boolean;
  published_by_external: boolean;
}

export interface PackageInventory {
  items: PackageInventoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface StaleImage {
  id: number;
  org: string;
  repo: string | null;
  name: string;
  last_published_at: string | null;
  days_since_rebuild: number;
  owner: string | null;
}

export interface StaleImageList {
  images: StaleImage[];
  total: number;
  threshold_days: number;
}

/* ── API functions ──────────────────────────────────────────────────────── */

export function getPackageSummary(): Promise<PackageSummary> {
  return api.get<PackageSummary>('/packages/summary');
}

export function getPackageAlerts(params?: {
  status?: string;
  severity?: string;
  page?: number;
  page_size?: number;
}): Promise<PackageAlertList> {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set('status', params.status);
  if (params?.severity) searchParams.set('severity', params.severity);
  if (params?.page) searchParams.set('page', String(params.page));
  if (params?.page_size) searchParams.set('page_size', String(params.page_size));
  const qs = searchParams.toString();
  return api.get<PackageAlertList>(`/packages/alerts${qs ? `?${qs}` : ''}`);
}

export function getPackageInventory(params?: {
  type?: string;
  visibility?: string;
  page?: number;
  page_size?: number;
}): Promise<PackageInventory> {
  const searchParams = new URLSearchParams();
  if (params?.type) searchParams.set('type', params.type);
  if (params?.visibility) searchParams.set('visibility', params.visibility);
  if (params?.page) searchParams.set('page', String(params.page));
  if (params?.page_size) searchParams.set('page_size', String(params.page_size));
  const qs = searchParams.toString();
  return api.get<PackageInventory>(`/packages/inventory${qs ? `?${qs}` : ''}`);
}

export function getStaleImages(days?: number): Promise<StaleImageList> {
  const qs = days ? `?days=${days}` : '';
  return api.get<StaleImageList>(`/packages/stale-images${qs}`);
}
