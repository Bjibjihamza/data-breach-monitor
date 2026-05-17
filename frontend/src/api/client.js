export class ApiError extends Error {
  constructor(message, { status, payload } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

function buildUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, value);
    }
  });
  return `${url.pathname}${url.search}`;
}

export async function request(path, { method = 'GET', params, body } = {}) {
  const response = await fetch(buildUrl(path, params), {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined
  });

  let payload = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }

  if (!response.ok) {
    const detail = payload?.detail?.error || payload?.detail || payload?.error || response.statusText;
    throw new ApiError(String(detail), { status: response.status, payload });
  }

  return payload;
}

export const getJson = (path, params) => request(path, { params });
export const postJson = (path, body) => request(path, { method: 'POST', body });
export const patchJson = (path, body) => request(path, { method: 'PATCH', body });
