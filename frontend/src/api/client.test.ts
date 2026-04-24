import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiFetch, ApiError } from './client';

function mockFetchResponse(options: {
  status: number;
  body?: unknown;
  contentType?: string;
  headers?: Record<string, string>;
}) {
  const { status, body, contentType = 'application/json', headers = {} } = options;

  const responseHeaders = new Headers({ 'Content-Type': contentType, ...headers });

  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: responseHeaders,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(typeof body === 'string' ? body : JSON.stringify(body)),
  } as unknown as Response);
}

describe('apiFetch', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('prepends /api/v1 to request URLs', async () => {
    const mockFetch = mockFetchResponse({ status: 200, body: { ok: true } });
    vi.stubGlobal('fetch', mockFetch);

    await apiFetch('/users');

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/users',
      expect.objectContaining({ method: 'GET' }),
    );
  });

  it('throws ApiError on non-OK responses', async () => {
    const mockFetch = mockFetchResponse({
      status: 422,
      body: { error: 'Validation failed' },
    });
    vi.stubGlobal('fetch', mockFetch);

    await expect(apiFetch('/items')).rejects.toThrow(ApiError);
    await expect(apiFetch('/items')).rejects.toMatchObject({
      status: 422,
      body: { error: 'Validation failed' },
    });
  });

  it('parses JSON responses', async () => {
    const mockFetch = mockFetchResponse({
      status: 200,
      body: { id: 1, name: 'test' },
    });
    vi.stubGlobal('fetch', mockFetch);

    const result = await apiFetch<{ id: number; name: string }>('/items/1');
    expect(result).toEqual({ id: 1, name: 'test' });
  });

  it('returns undefined for 204 responses', async () => {
    const mockFetch = mockFetchResponse({ status: 204, contentType: '' });
    vi.stubGlobal('fetch', mockFetch);

    const result = await apiFetch('/items/1');
    expect(result).toBeUndefined();
  });

  it('sets Accept header to application/json', async () => {
    const mockFetch = mockFetchResponse({ status: 200, body: {} });
    vi.stubGlobal('fetch', mockFetch);

    await apiFetch('/test');

    const calledHeaders = mockFetch.mock.calls[0][1].headers as Headers;
    expect(calledHeaders.get('Accept')).toBe('application/json');
  });
});

describe('apiFetch – CSRF token', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
  });

  it('sends CSRF token header on mutating requests', async () => {
    // Dynamically import to get a fresh module with csrfToken = null
    const { apiFetch: freshApiFetch } = await import('./client');

    // First request: server returns a CSRF token in the response
    const mockFetchWithCsrf = mockFetchResponse({
      status: 200,
      body: { ok: true },
      headers: { 'X-CSRF-Token': 'server-csrf-token' },
    });
    vi.stubGlobal('fetch', mockFetchWithCsrf);
    await freshApiFetch('/init');

    // Second request: POST should include the stored CSRF token
    const mockFetchPost = mockFetchResponse({ status: 200, body: { created: true } });
    vi.stubGlobal('fetch', mockFetchPost);
    await freshApiFetch('/action', { method: 'POST', body: JSON.stringify({ a: 1 }) });

    const sentHeaders = mockFetchPost.mock.calls[0][1].headers as Headers;
    expect(sentHeaders.get('X-CSRF-Token')).toBe('server-csrf-token');
  });

  it('does not send CSRF token on GET requests', async () => {
    const { apiFetch: freshApiFetch } = await import('./client');

    // Seed the CSRF token
    const seedFetch = mockFetchResponse({
      status: 200,
      body: {},
      headers: { 'X-CSRF-Token': 'seed-token' },
    });
    vi.stubGlobal('fetch', seedFetch);
    await freshApiFetch('/seed');

    // GET request should NOT include CSRF token
    const getFetch = mockFetchResponse({ status: 200, body: {} });
    vi.stubGlobal('fetch', getFetch);
    await freshApiFetch('/data');

    const sentHeaders = getFetch.mock.calls[0][1].headers as Headers;
    expect(sentHeaders.get('X-CSRF-Token')).toBeNull();
  });
});

describe('apiFetch – 401 redirect', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
  });

  it('redirects to /login on 401 response', async () => {
    const { apiFetch: freshApiFetch } = await import('./client');

    const replaceSpy = vi.fn();
    vi.stubGlobal('location', { replace: replaceSpy });

    const mockFetch401 = mockFetchResponse({ status: 401, body: { detail: 'Unauthorized' } });
    vi.stubGlobal('fetch', mockFetch401);

    // apiFetch rejects with Error('Unauthorized') on 401 and also calls location.replace('/login')
    await expect(freshApiFetch('/protected')).rejects.toThrow('Unauthorized');

    expect(replaceSpy).toHaveBeenCalledWith('/login');
  });
});
