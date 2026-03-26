import { api } from './client';
import type { EventResponse, EventListResponse, EventListParams } from '../types/events';

export function listEvents(params: EventListParams = {}): Promise<EventListResponse> {
  return api.get<EventListResponse>('/events', params as Record<string, string | number | boolean | undefined>);
}

export function getEvent(id: number): Promise<EventResponse> {
  return api.get<EventResponse>(`/events/${id}`);
}

export function getRawEvent(id: number): Promise<Record<string, unknown>> {
  return api.get<Record<string, unknown>>(`/events/${id}/raw`);
}
