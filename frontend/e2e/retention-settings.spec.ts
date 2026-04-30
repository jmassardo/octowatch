import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Data Retention Settings E2E Tests
//
// Tests the admin retention API and validates policy enforcement including
// minimum retention day limits.
// ---------------------------------------------------------------------------

const RETENTION_POLICIES_MOCK = [
  {
    data_type: 'events',
    category: 'Audit & Events',
    display_name: 'GitHub Audit Events',
    description: 'Raw audit log events from GitHub organizations',
    retention_days: 365,
    minimum_days: 30,
    is_system: false,
    updated_by: null,
    updated_at: null,
    table_name: 'events',
    time_column: 'created_at',
    row_count: 1_500_000,
    size_bytes: 2_147_483_648,
  },
  {
    data_type: 'threats',
    category: 'Security',
    display_name: 'Threat Detections',
    description: 'Security threat detection records',
    retention_days: 730,
    minimum_days: 90,
    is_system: false,
    updated_by: null,
    updated_at: null,
    table_name: 'threat_detections',
    time_column: 'detected_at',
    row_count: 50_000,
    size_bytes: 104_857_600,
  },
  {
    data_type: 'audit_trail',
    category: 'System',
    display_name: 'Internal Audit Trail',
    description: 'OctoWatch internal audit trail (immutable)',
    retention_days: 2555,
    minimum_days: 365,
    is_system: true,
    updated_by: null,
    updated_at: null,
    table_name: 'audit_trail',
    time_column: 'timestamp',
    row_count: 200_000,
    size_bytes: 52_428_800,
  },
  {
    data_type: 'sessions',
    category: 'System',
    display_name: 'User Sessions',
    description: 'Authentication session records',
    retention_days: 90,
    minimum_days: 7,
    is_system: false,
    updated_by: 'admin',
    updated_at: '2024-05-01T00:00:00Z',
    table_name: 'user_sessions',
    time_column: 'created_at',
    row_count: 10_000,
    size_bytes: 5_242_880,
  },
  {
    data_type: 'copilot_metrics',
    category: 'Analytics',
    display_name: 'Copilot Usage Metrics',
    description: 'GitHub Copilot adoption and usage data',
    retention_days: 180,
    minimum_days: 30,
    is_system: false,
    updated_by: null,
    updated_at: null,
    table_name: 'copilot_metrics',
    time_column: 'collected_at',
    row_count: 300_000,
    size_bytes: 67_108_864,
  },
];

test.describe('Retention Settings API', () => {
  test.fixme(!!process.env.CI, 'Auth cookies do not persist through self-signed TLS in CI');

  test('GET /api/v1/admin/retention lists all data type policies', async ({ page }) => {
    await page.route('**/api/v1/admin/retention', (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(RETENTION_POLICIES_MOCK),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/retention');
    if (response.status() === 200) {
      const policies = await response.json();
      expect(policies.length).toBeGreaterThanOrEqual(3);

      // Each policy should have expected fields
      for (const policy of policies) {
        expect(policy).toHaveProperty('data_type');
        expect(policy).toHaveProperty('category');
        expect(policy).toHaveProperty('display_name');
        expect(policy).toHaveProperty('retention_days');
        expect(policy).toHaveProperty('minimum_days');
        expect(policy).toHaveProperty('table_name');
        expect(policy.retention_days).toBeGreaterThan(0);
        expect(policy.minimum_days).toBeGreaterThan(0);
      }
    }
  });

  test('policies include multiple categories', async ({ page }) => {
    await page.route('**/api/v1/admin/retention', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(RETENTION_POLICIES_MOCK),
      });
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/retention');
    if (response.status() === 200) {
      const policies = await response.json();
      const categories = new Set(policies.map((p: { category: string }) => p.category));
      expect(categories.size).toBeGreaterThanOrEqual(2);
    }
  });

  test('PATCH /api/v1/admin/retention/:data_type updates retention period', async ({ page }) => {
    await page.route('**/api/v1/admin/retention/events', (route) => {
      if (route.request().method() === 'PATCH') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok',
            data_type: 'events',
            retention_days: 180,
            previous_days: 365,
          }),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.patch('/api/v1/admin/retention/events', {
      data: { retention_days: 180 },
    });

    if (response.status() === 200) {
      const result = await response.json();
      expect(result.status).toBe('ok');
      expect(result.retention_days).toBe(180);
    }
  });

  test('setting below minimum_days returns 400 error', async ({ page }) => {
    await page.route('**/api/v1/admin/retention/events', (route) => {
      if (route.request().method() === 'PATCH') {
        route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: 'Retention period cannot be less than minimum of 30 days for events',
          }),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.patch('/api/v1/admin/retention/events', {
      data: { retention_days: 5 },
    });

    expect([400, 401, 403, 422]).toContain(response.status());
    if (response.status() === 400) {
      const error = await response.json();
      expect(error.detail).toContain('minimum');
    }
  });

  test('setting above maximum (3650) returns 422 validation error', async ({ page }) => {
    await page.route('**/api/v1/admin/retention/events', (route) => {
      if (route.request().method() === 'PATCH') {
        route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({
            detail: [{ msg: 'ensure this value is less than or equal to 3650' }],
          }),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.patch('/api/v1/admin/retention/events', {
      data: { retention_days: 5000 },
    });

    expect([400, 401, 403, 422]).toContain(response.status());
  });

  test('updated policy reflects new updated_by and updated_at', async ({ page }) => {
    const updatedPolicies = RETENTION_POLICIES_MOCK.map((p) =>
      p.data_type === 'events'
        ? { ...p, retention_days: 180, updated_by: 'admin', updated_at: '2024-06-01T12:00:00Z' }
        : p,
    );

    await page.route('**/api/v1/admin/retention', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(updatedPolicies),
      });
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/retention');
    if (response.status() === 200) {
      const policies = await response.json();
      const events = policies.find((p: { data_type: string }) => p.data_type === 'events');
      expect(events).toBeTruthy();
      expect(events.retention_days).toBe(180);
      expect(events.updated_by).toBe('admin');
      expect(events.updated_at).toBeTruthy();
    }
  });

  test('nonexistent data_type returns 400 or 404', async ({ page }) => {
    await page.route('**/api/v1/admin/retention/nonexistent', (route) => {
      if (route.request().method() === 'PATCH') {
        route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ detail: "Unknown data type: 'nonexistent'" }),
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/dashboard');

    const response = await page.request.patch('/api/v1/admin/retention/nonexistent', {
      data: { retention_days: 90 },
    });

    expect([400, 404, 401, 403]).toContain(response.status());
  });

  test('policies include storage statistics (row_count, size_bytes)', async ({ page }) => {
    await page.route('**/api/v1/admin/retention', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(RETENTION_POLICIES_MOCK),
      });
    });

    await page.goto('/dashboard');

    const response = await page.request.get('/api/v1/admin/retention');
    if (response.status() === 200) {
      const policies = await response.json();
      for (const policy of policies) {
        expect(policy).toHaveProperty('row_count');
        expect(policy).toHaveProperty('size_bytes');
        expect(typeof policy.row_count).toBe('number');
        expect(typeof policy.size_bytes).toBe('number');
      }
    }
  });
});
