import { api } from './client';

export interface ActionsResponse {
  actions: string[];
}

export interface FieldsResponse {
  fields: string[];
}

export interface ActorsResponse {
  actors: string[];
}

export interface ReposResponse {
  repos: string[];
}

export interface OrgsResponse {
  orgs: string[];
}

export interface NamespacesResponse {
  namespaces: string[];
}

export function getSuggestedActions(): Promise<ActionsResponse> {
  return api.get<ActionsResponse>('/suggestions/actions');
}

export function getSuggestedFields(): Promise<FieldsResponse> {
  return api.get<FieldsResponse>('/suggestions/fields');
}

export function getSuggestedActors(): Promise<ActorsResponse> {
  return api.get<ActorsResponse>('/suggestions/actors');
}

export function getSuggestedRepos(): Promise<ReposResponse> {
  return api.get<ReposResponse>('/suggestions/repos');
}

export function getSuggestedOrgs(): Promise<OrgsResponse> {
  return api.get<OrgsResponse>('/suggestions/orgs');
}

export function getSuggestedNamespaces(): Promise<NamespacesResponse> {
  return api.get<NamespacesResponse>('/suggestions/namespaces');
}
