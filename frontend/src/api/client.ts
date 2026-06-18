import { saveCurrentRoute } from '../hooks/useSessionTimeout';

/** Module-level CSRF token store. Updated on every response that carries X-CSRF-Token. */
let csrfToken: string | null = null;

/** Notify session timeout hook that an API call succeeded (resets inactivity timer). */
function notifyApiActivity(): void {
  window.dispatchEvent(new CustomEvent('octowatch:api-activity'));
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase();

  const headers = new Headers(options.headers);

  headers.set('Accept', 'application/json');

  if (!headers.has('Content-Type') && options.body != null && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  if (MUTATING_METHODS.has(method) && csrfToken !== null) {
    headers.set('X-CSRF-Token', csrfToken);
  }

  const response = await fetch(`/api/v1${path}`, {
    ...options,
    method,
    headers,
    credentials: 'include',
  });

  const newCsrf = response.headers.get('X-CSRF-Token');
  if (newCsrf !== null) {
    csrfToken = newCsrf;
  }

  if (response.status === 401) {
    saveCurrentRoute();
    window.location.replace('/login');
    return Promise.reject(new Error('Unauthorized'));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  let body: unknown;
  const contentType = response.headers.get('Content-Type') ?? '';
  if (contentType.includes('application/json')) {
    body = await response.json();
  } else {
    body = await response.text();
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      body,
      `API ${method} ${path} failed with status ${response.status}`,
    );
  }

  notifyApiActivity();
  return body as T;
}

function buildQuery(params: object): string {
  const p = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      p.set(key, String(value));
    }
  }
  return p.toString();
}

export const api = {
  get: <T>(path: string, params?: object) => {
    const url = params ? `${path}?${buildQuery(params)}` : path;
    return apiFetch<T>(url);
  },
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  put: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: 'PUT',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, {
      method: 'PATCH',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: 'DELETE' }),
};
