import { api } from './client';
import type { MeResponse } from '../types/auth';

export function getMe(): Promise<MeResponse> {
  return api.get<MeResponse>('/auth/me');
}

export function logout(): Promise<void> {
  return api.post<void>('/auth/logout');
}
