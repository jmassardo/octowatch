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

export function getSuggestedActions(): Promise<ActionsResponse> {
  return api.get<ActionsResponse>('/suggestions/actions');
}

export function getSuggestedFields(): Promise<FieldsResponse> {
  return api.get<FieldsResponse>('/suggestions/fields');
}

export function getSuggestedActors(): Promise<ActorsResponse> {
  return api.get<ActorsResponse>('/suggestions/actors');
}
