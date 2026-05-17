import { getJson, patchJson } from './client.js';

export const getDetections = (params = {}) => getJson('/detections', params);

export const updateDetectionStatus = (detectionHash, status, reviewNote = '') =>
  patchJson(`/detections/${encodeURIComponent(detectionHash)}/status`, {
    status,
    review_note: reviewNote || null,
    reviewed_by: 'dashboard'
  });
