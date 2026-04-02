import { api } from './client';
import type {
  DetectionResponse,
  DetectionListResponse,
  UpdateDetectionStatusRequest,
  AssignDetectionRequest,
} from '../types/detections';

export interface DetectionListParams {
  status?: string;
  severity?: string;
  org?: string;
  page?: number;
  page_size?: number;
}

export function listDetections(params: DetectionListParams = {}): Promise<DetectionListResponse> {
  return api.get<DetectionListResponse>(
    '/detections',
    params as Record<string, string | number | boolean | undefined>,
  );
}

export function getDetection(id: number): Promise<DetectionResponse> {
  return api.get<DetectionResponse>(`/detections/${id}`);
}

export function updateDetectionStatus(
  id: number,
  req: UpdateDetectionStatusRequest,
): Promise<DetectionResponse> {
  return api.patch<DetectionResponse>(`/detections/${id}/status`, req);
}

export function assignDetection(
  id: number,
  req: AssignDetectionRequest,
): Promise<DetectionResponse> {
  return api.patch<DetectionResponse>(`/detections/${id}/assign`, req);
}

export function suppressDetection(id: number): Promise<DetectionResponse> {
  return api.post<DetectionResponse>(`/detections/${id}/suppress`);
}

export function deleteDetection(id: number): Promise<void> {
  return api.delete<void>(`/detections/${id}`);
}
