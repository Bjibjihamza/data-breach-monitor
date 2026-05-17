import { getJson } from './client.js';

export const getSummary = () => getJson('/analytics/summary');
export const getSourceHealth = () => getJson('/analytics/source-health');
export const getCollectionRuns = (params = {}) => getJson('/analytics/collection-runs', params);
export const getCharts = (params = {}) => getJson('/analytics/charts', params);
export const getCorrelations = (params = {}) => getJson('/analytics/correlations', params);
export const getIntelligenceSummary = (params = {}) => getJson('/analytics/intelligence-summary', params);
export const getSourceDiagnostics = () => getJson('/analytics/source-diagnostics');
