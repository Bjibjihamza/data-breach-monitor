import { getJson } from './client.js';

export const getCollectionState = () => getJson('/debug/collection-state');
export const getGitHubConfig = () => getJson('/debug/github-config');
export const getGoogleAlertsConfig = () => getJson('/debug/google-alerts-config');
export const getTelegramConfig = () => getJson('/debug/telegram-config');
export const getHealth = () => getJson('/health');
