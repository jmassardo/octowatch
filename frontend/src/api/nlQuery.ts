import { api } from './client';

export interface NLInterpretation {
  sql: string;
  description: string;
  confidence: number;
}

export interface NLQueryResponse {
  interpretations: NLInterpretation[];
  raw_query: string;
}

export function translateNLQuery(body: { query: string }) {
  return api.post<NLQueryResponse>('/query/nl', body);
}
