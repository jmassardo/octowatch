import { api } from './client';

export interface NLInterpretation {
  sql: string;
  description: string;
  confidence: number;
}

export function translateNLQuery(body: { query: string }): Promise<NLInterpretation[]> {
  return api.post<NLInterpretation[]>('/query/nl', body);
}
